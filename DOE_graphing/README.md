<!-- @format -->

# DOE Post-Processing Template User Guide

This is a Jupyter Notebook template for design-of-experiments (DOE) data post-processing and visualization.
The notebook reads in an Excel file of yields, parses key parameters and any extra metadata columns, and generates interactive plots of Yield vs. experimental factors.

---

## Requirements

- **Python** 3.11 or higher
- **Jupyter Notebook** or **JupyterLab**
- **Install Required libraries:**
  In the terminal, run:

  ```sh
  pip install plotly scikit-learn scipy pandas numpy
  ```

---

## Input Data

The input Excel file should contain at least the following columns at the top of the first sheet:

Here's is an example of the required columns, the name of these columns can be different.

| Run order | Temperature (°C) | Current (mA) | Rotation (RPM) | Yield (%) |
| --------- | ---------------- | ------------ | -------------- | --------- |

Any additional columns (e.g., `Notebook`, `Operator`, `Notes`) will be treated as metadata.

Example file: `Results.xlsx`

| Run order | Temperature (°C) | Current (mA) | Rotation (RPM) | Yield (%) | Notebook |
| --------- | ---------------- | ------------ | -------------- | --------- | -------- |
| 1         | 15               | 15           | 100            | 50        | XXX00001 |
| 2         | 45               | 15           | 100            | 60        | XXX00002 |
| ...       | ...              | ...          | ...            | ...       | ...      |

---

## Usage

1. Download the notebook:
   `DOE_template.ipynb`

2. Place the Excel results file (e.g., `Results.xlsx`) in the same directory as the notebook.

3. Open `DOE_template.ipynb` Jupyter Notebook or JupyterLab

4. Edit the top-most cell to point to the Excel file and include any extra columns you want to include as metadata:

   ```python
   # Specify your results filename:
   filename = "Results.xlsx"

   # List any columns beyond 'Yield (%)' to include as metadata:
   extra_columns = ["Notebook"]
   ```

5. Run all the remaining cells in the notebook.

The notebook will load and preprocess the data, producing an interactive Plotly figure showing how Yield varies with Temperature, Current, and Rotation.
Hover-tooltips include any `extra_columns` you specified.

---

## Output

Plot will be saved as html files in the same directory as the notebook.

- **Interactive Plots:**
  - **3D Scatter Plot:** Visualizes Yield versus experimental factors, with color and size encoding, and hover tooltips displaying metadata.
  - **3D Scatter Plot (Predicted Data):** Shows predicted Yield values across experimental factors.
  - **3D Scatter Plot (Min/Max Predicted Data):** Highlights only the minimum and maximum predicted Yield points.
  - **3D Surface Plot:** Displays the maximum predicted Yield as a surface over experimental factors.

---

For questions or contributions, please open an issue or pull request on the [GitHub repository](https://github.com/intel00000/EChem_Auto_Potential_Optimization).
