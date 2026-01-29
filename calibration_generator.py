"""Calibration coefficient generator for sensor calibration.

Generates calibration terms (c, x1, x2) using least-squares fitting.

Models supported:
    - Polynomial order >= 1: y_cal = c + x1 * y_raw + x2 * y_raw^2 + ...

Usage:
  python calibration_generator.py

Or import and use programmatically:
    from calibration_generator import CalibrationGenerator
    gen = CalibrationGenerator()
    coeffs = gen.fit_data_coeffs(setpoints, measured_values, order=3)
"""

import argparse
import csv
from pathlib import Path
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.axes import Axes
from typing import Tuple, List, Sequence, cast


class CalibrationGenerator:
    """Generate calibration coefficients from setpoint and measured data."""

    def __init__(self):
        """Initialize the calibration generator."""
        pass

    def _validate_inputs(
        self,
        setpoints: list[float],
        measured: list[float],
        order: int,
    ) -> None:
        if len(setpoints) != len(measured):
            raise ValueError("setpoints and measured must have same length")

        if order < 1:
            raise ValueError("order must be >= 1")

        if len(setpoints) < order + 1:
            raise ValueError(f"Need at least {order + 1} data points for order {order}")

    def _compute_metrics(
        self,
        setpoints_arr: np.ndarray,
        calibrated_arr: np.ndarray,
    ) -> Tuple[float, float, float, float]:
        residuals = setpoints_arr - calibrated_arr
        ss_res = np.sum(residuals ** 2)
        ss_tot = np.sum((setpoints_arr - np.mean(setpoints_arr)) ** 2)
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

        rmse = float(np.sqrt(np.mean(residuals ** 2)))
        measurement_range = np.max(setpoints_arr) - np.min(setpoints_arr)
        normalized_rmse = (rmse / measurement_range * 100) if measurement_range != 0 else 0.0
        max_error = float(np.max(np.abs(residuals)))

        return float(r_squared), rmse, float(normalized_rmse), max_error

    def fit_data_coeffs(
        self,
        setpoints: list[float],
        measured: list[float],
        order: int = 1,
    ) -> List[float]:
        """Fit calibration data and return full polynomial coefficients.

        Args:
            setpoints: List of reference/setpoint values
            measured: List of measured/actual values from sensor
            order: Polynomial order (>= 1)

        Returns:
            List of coefficients in descending order of powers (np.polyfit format).

        Raises:
            ValueError: If data is invalid or order is less than 1
        """
        self._validate_inputs(setpoints, measured, order)

        setpoints_arr = np.array(setpoints, dtype=float)
        measured_arr = np.array(measured, dtype=float)

        coeffs = np.polyfit(measured_arr, setpoints_arr, order)
        return [float(c) for c in coeffs]

    def calculate_calibrated(
        self,
        raw_value: float,
        coeffs_desc: Sequence[float],
    ) -> float:
        """Calculate calibrated value using coefficients.

        Args:
            raw_value: Raw measured value from sensor
            coeffs_desc: Polynomial coefficients in descending order

        Returns:
            Calibrated value from polynomial coefficients
        """
        return float(np.polyval(coeffs_desc, raw_value))

    def print_calibration_summary(
        self,
        setpoints: list[float],
        measured: list[float],
        coeffs_desc: Sequence[float],
        order: int,
    ) -> None:
        """Print calibration summary with statistics.

        Args:
            setpoints: Original setpoint data
            measured: Original measured data
            coeffs_desc: Polynomial coefficients in descending order
            order: Polynomial order
        """
        setpoints_arr = np.array(setpoints, dtype=float)
        calibrated = np.polyval(coeffs_desc, np.array(measured, dtype=float))

        r_squared, rmse, normalized_rmse, max_error = self._compute_metrics(
            setpoints_arr, calibrated
        )
        
        print(f"\nFitness Score:")
        print(f"  R² (fit quality):   {r_squared:.6f}")
        print(f"  RMSE:               {rmse:.6f}")
        print(f"  Normalized RMSE:    {normalized_rmse:.2f}%")
        print(f"  Max Error:          {max_error:.6f}")
        print(f"  Num Points:         {len(setpoints)}")
        
        max_power = max(1, order)
        print("\nCoefficients:")
        for i, coef in enumerate(reversed(coeffs_desc)):
            power = i
            if power > max_power:
                break
            label = "c" if power == 0 else f"x{power}"
            precision = 6
            coef_display = 0.0 if abs(coef) < 10 ** (-(precision + 1)) else coef
            print(f"  {label:<3}: {coef_display: .{precision}f}")


class CalibrationPlotter:
    """Plot calibration results."""

    def plot(
        self,
        setpoints: list[float],
        measured: list[float],
        coeffs_desc: Sequence[float],
    ) -> None:
        x = np.array(setpoints, dtype=float)
        y_measured = np.array(measured, dtype=float)
        y_calibrated = np.polyval(coeffs_desc, y_measured)

        x_min = float(np.min(x))
        x_max = float(np.max(x))
        y_min = float(np.min([y_measured.min(), y_calibrated.min(), x_min]))
        y_max = float(np.max([y_measured.max(), y_calibrated.max(), x_max]))

        x_pad = (x_max - x_min) * 0.05 if x_max != x_min else 1.0
        y_pad = (y_max - y_min) * 0.05 if y_max != y_min else 1.0

        fig, axes = plt.subplots(1, 2, figsize=(12, 5), constrained_layout=True)
        if len(axes) != 2:
            raise ValueError("Expected two axes from subplots(1, 2)")
        ax_left, ax_right = cast(list[Axes], list(axes))

        ax_left.scatter(x, y_measured, label="Measured", color="tab:blue")
        ax_left.plot([x_min, x_max], [x_min, x_max], "k--", label="Perfect")
        ax_left.set_title("Setpoint vs Measured")
        ax_left.set_xlabel("Setpoint")
        ax_left.set_ylabel("Measured")
        ax_left.set_xlim(x_min - x_pad, x_max + x_pad)
        ax_left.set_ylim(y_min - y_pad, y_max + y_pad)
        ax_left.grid(True, linestyle="--", alpha=0.4)
        ax_left.legend()

        ax_right.scatter(x, y_calibrated, label="Calibrated", color="tab:green")
        ax_right.plot([x_min, x_max], [x_min, x_max], "k--", label="Perfect")
        ax_right.set_title("Setpoint vs Calibrated")
        ax_right.set_xlabel("Setpoint")
        ax_right.set_ylabel("Calibrated")
        ax_right.set_xlim(x_min - x_pad, x_max + x_pad)
        ax_right.set_ylim(y_min - y_pad, y_max + y_pad)
        ax_right.grid(True, linestyle="--", alpha=0.4)
        ax_right.legend()

        plt.show(block=False)
        fig.canvas.draw_idle()
        plt.pause(0.1)


def _read_csv_points(file_path: Path) -> Tuple[List[float], List[float]]:
    """Read setpoint and measured pairs from a CSV file.

    The CSV must include two columns: setpoint and measured.
    Column names are case-insensitive. A header row is required.
    """
    if not file_path.exists():
        raise ValueError(f"File not found: {file_path}")

    with file_path.open(newline="", encoding="utf-8") as csvfile:
        reader = csv.DictReader(csvfile)
        if reader.fieldnames is None:
            raise ValueError("CSV file must include a header row")

        fieldnames = {name.strip().lower(): name for name in reader.fieldnames}
        if "setpoint" not in fieldnames or "measured" not in fieldnames:
            raise ValueError("CSV header must include 'setpoint' and 'measured' columns")

        setpoints: List[float] = []
        measured_values: List[float] = []

        for row_num, row in enumerate(reader, start=2):
            try:
                setpoint_raw = row[fieldnames["setpoint"]]
                measured_raw = row[fieldnames["measured"]]
                if setpoint_raw is None or measured_raw is None:
                    raise ValueError
                setpoints.append(float(setpoint_raw))
                measured_values.append(float(measured_raw))
            except (ValueError, TypeError):
                raise ValueError(f"Invalid numeric data at CSV line {row_num}")

    if not setpoints:
        raise ValueError("CSV file contains no data rows")

    return setpoints, measured_values


def run_calibration_from_csv(file_path: Path, order: int) -> None:
    """Run calibration using CSV input."""
    gen = CalibrationGenerator()
    plotter = CalibrationPlotter()

    print()
    print(f"csv_file: {file_path}")
    print(f"order   : {order}")

    try:
        setpoints, measured_values = _read_csv_points(file_path)
        coeffs = gen.fit_data_coeffs(setpoints, measured_values, order=order)
        gen.print_calibration_summary(
            setpoints, measured_values, coeffs, order=order
        )
        plotter.plot(setpoints, measured_values, coeffs)
        _wait_for_exit()
        plt.close("all")

    except ValueError as e:
        print(f"\nError: {e}")


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate calibration coefficients from CSV data."
    )
    parser.add_argument(
        "csv_file",
        type=Path,
        help="Path to CSV file with columns: setpoint, measured",
    )
    parser.add_argument(
        "--order",
        type=int,
        default=1,
        help="Polynomial order (>= 1)",
    )
    return parser.parse_args()


def _wait_for_exit() -> None:
    try:
        input("\nPress any key to exit...")
    except EOFError:
        pass


if __name__ == "__main__":
    args = _parse_args()
    run_calibration_from_csv(args.csv_file, args.order)
