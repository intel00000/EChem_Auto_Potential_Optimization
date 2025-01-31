import os
import time
from datetime import datetime, timezone
from collections import defaultdict
import pytz


tz = pytz.timezone("America/Chicago")  # CST/CDT timezone
timestamp = int(time.time())  # Get a timestamp for cache busting

# List all HTML files index.html
html_files = [f for f in os.listdir(".") if f.endswith(".html") and f != "index.html"]
# Organize files by prefix (first space-separated word in the filename)
file_groups = defaultdict(list)
for filename in sorted(html_files):
    display_name = filename.replace("_", " ").replace(".html", "")
    prefix = display_name.split(" ", 1)[0]  # First word as prefix
    file_groups[prefix].append((filename, display_name))


# Writing the index.html file
with open("index.html", "w") as index_file:
    index_file.write(
        """<!DOCTYPE html>
<html>
	<head>
		<meta charset="UTF-8">
		<meta http-equiv="cache-control" content="no-cache, must-revalidate, post-check=0, pre-check=0" />
		<meta http-equiv="cache-control" content="max-age=0" />
		<meta http-equiv="expires" content="0" />
		<meta http-equiv="expires" content="Tue, 01 Jan 1980 1:00:00 GMT" />
		<meta http-equiv="pragma" content="no-cache" />
		<title>Available Pages for EChem_Auto_Potential_Optimization repo</title>
		<link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.min.css" rel="stylesheet" integrity="sha384-QWTKZyjpPEjISv5WaRU9OFeRpok6YctnYmDr5pNlyT2bRjXh0JMhjY6hW+ALEwIH" crossorigin="anonymous">
		<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js" integrity="sha384-YvpcrYf0tY3lHB60NNkmXc5s9fDVZLESaAA55NDzOxhy9GkcIdslK1eN7N6jIeHz" crossorigin="anonymous"></script>
        <script>
            function filterList() {
                let input = document.getElementById('searchInput').value.toLowerCase();
                let items = document.querySelectorAll('.list-group-item');
                let tabs = document.querySelectorAll('.nav-link'); // All tab buttons
                let tabContents = document.querySelectorAll('.tab-pane'); // All tab contents
                let foundInTabs = {}; // Track if any items are found in each tab
                let hasGlobalMatch = false; // Track if any item is visible at all

                // Hide all items initially
                items.forEach(item => {
                    let text = item.textContent.toLowerCase();
                    let parentTab = item.closest('.tab-pane').id;

                    if (text.includes(input)) {
                        item.style.display = '';
                        foundInTabs[parentTab] = true;
                        hasGlobalMatch = true;
                    } else {
                        item.style.display = 'none'; // Hide non-matching item
                    }
                });

                // Hide tabs with no results and activate the first one with results
                let firstVisibleTab = null;
                tabs.forEach(tab => {
                    let targetTab = tab.getAttribute('data-bs-target').substring(1); // Get tab-pane ID
                    let tabPane = document.getElementById(targetTab); // The tab content

                    if (foundInTabs[targetTab]) {
                        tab.style.display = ''; // Show tab
                        tabPane.style.display = ''; // Show tab content
                        if (!firstVisibleTab) {
                            firstVisibleTab = tab; // Mark first visible tab
                        }
                    } else {
                        tab.style.display = 'none'; // Hide tab
                        tabPane.style.display = 'none'; // Hide tab content
                    }
                });

                // If no matches at all, hide everything
                if (!hasGlobalMatch) {
                    tabs.forEach(tab => (tab.style.display = 'none')); // Hide all tabs
                    tabContents.forEach(tabPane => (tabPane.style.display = 'none')); // Hide all content
                } else if (firstVisibleTab) { // Activate the first visible tab
                    let tabInstance = new bootstrap.Tab(firstVisibleTab);
                    tabInstance.show();
                }
            }
        </script>
	</head>
	<body>
		<div class="container mt-5">
			<h2 class="mb-4">Available Pages for EChem_Auto_Potential_Optimization repo</h2>

			<!-- Search Input -->
			<input type="text" id="searchInput" class="form-control mb-3" onkeyup="filterList()" placeholder="Search pages...">

			<!-- Navigation Tabs -->
			<ul class="nav nav-tabs" id="navTabs" role="tablist">
"""
    )

    # Create tab navigation
    first = True
    for prefix in file_groups.keys():
        active_class = "active" if first else ""
        aria_selected = "true" if first else "false"
        index_file.write(
            f'			<li class="nav-item" role="presentation">\n'
            f'				<button class="nav-link {active_class}" id="{prefix}-tab" data-bs-toggle="tab" data-bs-target="#{prefix}" type="button" role="tab" aria-controls="{prefix}" aria-selected="{aria_selected}">\n'
            f"					{prefix}\n"
            f"				</button>\n"
            f"			</li>\n"
        )
        first = False

    index_file.write(
        "			</ul>\n			<div class='tab-content mt-3' id='navTabContent'>\n"
    )

    # Generate content for each tab
    first = True
    for prefix, files in file_groups.items():
        active_class = "show active" if first else ""
        index_file.write(
            f"				<div class='tab-pane fade {active_class}' id='{prefix}' role='tabpanel' aria-labelledby='{prefix}-tab'>\n"
            f"					<div class='list-group'>\n"
        )

        for filename, display_name in files:
            created_utc = datetime.fromtimestamp(
                os.path.getctime(filename), tz=timezone.utc
            )
            created_est = created_utc.astimezone(tz)  # Convert to EST/EDT dynamically
            created_time = created_est.strftime("%Y-%m-%d %H:%M")  # Removed UTC offset

            index_file.write(
                f"						<a href='{filename}?v={timestamp}' class='list-group-item list-group-item-action d-flex justify-content-between align-items-center'>\n"
                f"							{display_name}\n"
                f"							<small class='text-muted'>{created_time}</small>\n"
                f"						</a>\n"
            )

        index_file.write("					</div>\n				</div>\n")
        first = False

    index_file.write(
        """			</div>
		</div>
	</body>
</html>
"""
    )
