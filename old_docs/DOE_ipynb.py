import plotly
import pandas as pd
import numpy as np
import os

# print out all numpy array
np.set_printoptions(threshold=np.inf)

from itertools import product

from sklearn import datasets
from sklearn.gaussian_process import GaussianProcessRegressor

import plotly.graph_objects as go
import chart_studio.plotly as py


def bounds(data) -> list:
    mins = np.min(data, axis=0)
    maxs = np.max(data, axis=0)
    return [[mins_, maxs_] for mins_, maxs_ in zip(mins, maxs)]


# create the line space
def fullfact(bound_array, num_levels: int) -> np.ndarray:
    return np.array(
        list(
            product(
                *[np.linspace(min_, max_, num_levels) for min_, max_ in bound_array]
            )
        )
    )


def main():
    print(f"current path: {os.getcwd()}")
    # load the dataset
    data = pd.read_excel(
        "240905 Simulated Automated Screening Yields for DOE Practice.xlsx"
    )
    header = data.columns

    data = data.to_numpy()
    data = data[:, 1:]

    # find the max value of the 'Sim. Yields' column
    max_yield = np.argmax(data[:, 3])
    print(f"max_yield: {max_yield}")

    data[max_yield, :]

    regressor = GaussianProcessRegressor(random_state=0, kernel=None)

    regressor.fit(data[:, 0:3], data[:, 3])

    print(f"score: {regressor.score(data[:, 0:3], data[:, 3])}")

    result = fullfact(bounds(data[:, 0:3]), 20)

    print(f"result: {result}")

    # plot the original data
    fig = go.Figure(
        data=[
            go.Scatter3d(
                x=data[:, 0],
                y=data[:, 1],
                z=data[:, 3],
                mode="markers",
                marker=dict(size=4),
            )
        ]
    )
    fig.layout.scene.xaxis.title.text = "Temperature (°C)"
    fig.layout.scene.yaxis.title.text = "Rotation (RPM)"
    fig.layout.scene.zaxis.title.text = "yield"
    
    fig.show()


if __name__ == "__main__":
    main()