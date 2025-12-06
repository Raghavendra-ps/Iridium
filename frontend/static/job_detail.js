// Iridium-main/frontend/static/js/job_detail.js -- DEBUG VERSION

document.addEventListener("DOMContentLoaded", () => {
    const jobDetailContainer = document.getElementById("job-detail-page");
    if (!jobDetailContainer) return;

    const jobId = jobDetailContainer.dataset.jobId;
    const token = localStorage.getItem("access_token");
    const gridContainer = document.getElementById("data-grid-container");

    console.log(`[DEBUG] Script loaded for Job ID: ${jobId}`);
    gridContainer.innerHTML =
        '<p style="color: blue; font-weight: bold;">[DEBUG] JavaScript is running...</p>';

    const apiCall = async (url, options = {}) => {
        const defaultOptions = {
            headers: {
                Authorization: `Bearer ${token}`,
                "Content-Type": "application/json",
            },
        };
        const response = await fetch(url, { ...defaultOptions, ...options });
        if (response.status === 401) {
            localStorage.removeItem("access_token");
            window.location.href = "/login";
            throw new Error("Unauthorized");
        }
        return response;
    };

    async function fetchAndRenderData() {
        try {
            gridContainer.innerHTML =
                '<p style="color: blue; font-weight: bold;">[DEBUG] Fetching data from API...</p>';
            const response = await apiCall(`/api/v1/conversions/${jobId}/data`);

            if (!response.ok) {
                const errorText = await response.text();
                throw new Error(
                    `Server returned an error: ${response.status} ${errorText}`,
                );
            }

            const data = await response.json();
            gridContainer.innerHTML = `<p style="color: blue; font-weight: bold;">[DEBUG] Data received. Raw data:</p><pre style="border: 1px solid #ccc; padding: 10px; text-align: left;">${JSON.stringify(data, null, 2)}</pre>`;

            if (!Array.isArray(data) || data.length === 0) {
                gridContainer.innerHTML += `<p style="color: orange; font-weight: bold; margin-top: 10px;">[DEBUG] Data is empty. No grid to render.</p>`;
                return;
            }

            gridContainer.innerHTML += `<p style="color: blue; font-weight: bold; margin-top: 10px;">[DEBUG] Data is valid. Attempting to initialize Handsontable...</p>`;

            // This is the line that is likely failing silently.
            const hot = new Handsontable(gridContainer, {
                data: data,
                rowHeaders: true,
                colHeaders: Object.keys(data[0]),
                licenseKey: "non-commercial-and-evaluation",
                width: "100%",
                height: "auto",
                stretchH: "all",
                manualColumnResize: true,
                manualRowResize: true,
                contextMenu: true,
                dropdownMenu: true,
                filters: true,
            });

            // If we get here, it worked. Clear the debug messages and show the grid.
            gridContainer.innerHTML = ""; // Clear debug messages
            gridContainer.appendChild(hot.rootElement); // Re-attach the grid
            document.getElementById("actions-bar").style.display = "flex";
        } catch (error) {
            // If ANY error happens, it will be displayed directly on the page.
            gridContainer.innerHTML = `
                <div style="text-align: left; padding: 20px;">
                    <h3 style="color: red;">A CRITICAL JAVASCRIPT ERROR OCCURRED:</h3>
                    <p>The backend is working, but the script failed to draw the data grid.</p>
                    <hr style="margin: 10px 0;">
                    <p><strong>Error Message:</strong></p>
                    <pre style="background: #fff0f0; border: 1px solid red; padding: 10px; white-space: pre-wrap;">${error.message}</pre>
                    <p style="margin-top: 10px;"><strong>Stack Trace:</strong></p>
                    <pre style="background: #eee; border: 1px solid #ccc; padding: 10px; white-space: pre-wrap;">${error.stack}</pre>
                </div>
            `;
        }
    }

    // Simplified poller just to kick things off
    apiCall(`/api/v1/conversions/${jobId}/status`)
        .then((response) => response.json())
        .then((job) => {
            if (job.status === "AWAITING_VALIDATION") {
                fetchAndRenderData();
            } else {
                gridContainer.innerHTML = `<p>[DEBUG] Job status is '${job.status}'. Waiting for 'AWAITING_VALIDATION'.</p>`;
            }
        });
});
