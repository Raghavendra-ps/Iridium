// Iridium-main/frontend/static/js/job_detail.js

document.addEventListener("DOMContentLoaded", function () {
    const page = document.getElementById("job-detail-page");
    const jobId = page.dataset.jobId;
    const token = localStorage.getItem("access_token");

    const jobTitle = document.getElementById("job-title");
    const jobSubtitle = document.getElementById("job-subtitle");
    const jobStatusBadge = document.getElementById("job-status-badge");
    const gridContainer = document.getElementById("data-grid-container");
    const actionsBar = document.getElementById("actions-bar");
    const processBtn = document.getElementById("processBtn");

    let hot; // Handsontable instance
    let jobData = null;

    // --- 1. Define Column Configs (Mirroring Backend) ---
    // In a real app, fetch this from an API endpoint like /api/v1/conversions/config/{type}
    const GRID_CONFIGS = {
        attendance: [
            { data: "employee", title: "Employee ID", type: "text" },
            {
                data: "employee_name",
                title: "Name",
                type: "text",
                readOnly: true,
            },
            {
                data: "attendance_date",
                title: "Date",
                type: "date",
                dateFormat: "YYYY-MM-DD",
            },
            {
                data: "status",
                title: "Status",
                type: "dropdown",
                source: ["Present", "Absent", "On Leave", "Half Day"],
            },
            { data: "shift", title: "Shift", type: "text" },
            { data: "leave_type", title: "Leave Type", type: "text" },
        ],
        generic: [
            { data: "extracted_line", title: "Extracted Data", type: "text" },
        ],
    };

    async function fetchJobStatus() {
        try {
            const res = await fetch(`/api/v1/conversions/${jobId}/status`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) throw new Error("Failed to fetch status");
            const job = await res.json();

            renderHeader(job);

            // Handle States
            if (
                job.status === "AWAITING_VALIDATION" ||
                job.status === "SUBMISSION_FAILED"
            ) {
                if (!hot) {
                    await fetchDataAndInitGrid(job.target_doctype);
                }
                actionsBar.style.display = "flex";
            } else if (
                job.status === "PROCESSING" ||
                job.status === "UPLOADED"
            ) {
                gridContainer.innerHTML = `<p>Processing... Auto-refreshing in 3s.</p>`;
                setTimeout(fetchJobStatus, 3000);
            } else {
                gridContainer.innerHTML = `<p>Job Status: ${job.status}</p>`;
                actionsBar.style.display = "none";
            }
        } catch (e) {
            console.error(e);
        }
    }

    function renderHeader(job) {
        jobTitle.textContent = `Job #${job.id}: ${job.original_filename}`;
        jobSubtitle.textContent = `Type: ${job.target_doctype} | Created: ${job.created_at}`;
        jobStatusBadge.textContent = job.status;

        // Color coding
        if (job.status === "COMPLETED")
            jobStatusBadge.style.backgroundColor = "#dcfce7"; // green
        else if (job.status === "SUBMISSION_FAILED")
            jobStatusBadge.style.backgroundColor = "#fee2e2"; // red
    }

    async function fetchDataAndInitGrid(docType) {
        try {
            const res = await fetch(`/api/v1/conversions/${jobId}/data`, {
                headers: { Authorization: `Bearer ${token}` },
            });
            if (!res.ok) throw new Error("No data found");
            const jsonData = await res.json();

            // clear container
            gridContainer.innerHTML = "";

            // Select Columns based on DocType (case insensitive match)
            const typeKey = docType.toLowerCase();
            const columns = GRID_CONFIGS[typeKey] || GRID_CONFIGS["generic"];

            // Init Handsontable
            hot = new Handsontable(gridContainer, {
                data: jsonData,
                rowHeaders: true,
                colHeaders: columns.map((c) => c.title),
                columns: columns,
                licenseKey: "non-commercial-and-evaluation",
                height: "auto",
                width: "100%",
                minSpareRows: 1, // Allow adding rows
                stretchH: "all",
            });
        } catch (e) {
            gridContainer.innerHTML = `<p class="error">Failed to load data: ${e.message}</p>`;
        }
    }

    processBtn.addEventListener("click", async () => {
        if (!hot) return;

        const data = hot.getSourceData(); // Get raw data object
        // Filter out empty rows
        const cleanData = data.filter((row) => row.employee || row.status);

        processBtn.disabled = true;
        processBtn.textContent = "Submitting...";

        try {
            const res = await fetch(`/api/v1/conversions/${jobId}/submit`, {
                method: "POST",
                headers: {
                    Authorization: `Bearer ${token}`,
                    "Content-Type": "application/json",
                },
                body: JSON.stringify({ data: cleanData }),
            });

            if (res.ok) {
                alert("Submission started!");
                window.location.reload();
            } else {
                const err = await res.json();
                alert("Error: " + err.detail);
                processBtn.disabled = false;
                processBtn.textContent = "Process and Send";
            }
        } catch (e) {
            alert("Network error");
            processBtn.disabled = false;
        }
    });

    fetchJobStatus();
});
