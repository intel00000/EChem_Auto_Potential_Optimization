import os

# List all HTML files in the current directory excluding index.html
html_files = [f for f in os.listdir(".") if f.endswith(".html") and f != "index.html"]

# Start writing the index.html file
with open("index.html", "w") as index_file:
    index_file.write(
        """<!DOCTYPE html>
<html>
<head>
  <meta charset="UTF-8">
  <title>Available Pages</title>
  <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/bootstrap/5.3.2/css/bootstrap.min.css">
</head>
<body>
<div class="container mt-5">
  <h1 class="mb-4">Available Pages</h1>
  <div class="list-group">
"""
    )

    # Add a list item for each HTML file
    for filename in sorted(html_files):
        display_name = filename.replace("_", " ").replace(".html", "")
        index_file.write(
            f'    <a href="{filename}" class="list-group-item list-group-item-action">{display_name}</a>\n'
        )

    # Finish writing the index.html file
    index_file.write(
        """  </div>
</div>
</body>
</html>
"""
    )
