"""Calibration coefficient generator for sensor calibration.

Generates calibration terms (c, x1, x2) using least-squares fitting.

Models supported:
  - Linear: y_cal = x1 * y_raw + c
  - Quadratic: y_cal = c + x1 * y_raw + x2 * y_raw^2

Usage:
  python calibration_generator.py

Or import and use programmatically:
  from calibration_generator import CalibrationGenerator
  gen = CalibrationGenerator()
  c, x1, x2 = gen.fit_data(setpoints, measured_values, order=1)
"""

import numpy as np
from typing import Tuple


class CalibrationGenerator:
    """Generate calibration coefficients from setpoint and measured data."""

    def __init__(self):
        """Initialize the calibration generator."""
        pass

    def fit_data(
        self,
        setpoints: list[float],
        measured_values: list[float],
        order: int = 1,
    ) -> Tuple[float, float, float]:
        """Fit calibration data and return coefficients.

        Args:
            setpoints: List of reference/setpoint values
            measured_values: List of measured/actual values from sensor
            order: Polynomial order (1 for linear, 2 for quadratic)

        Returns:
            Tuple of (c, x1, x2) calibration coefficients
            For order=1: y_cal = x1 * y_raw + c (x2 = 0)
            For order=2: y_cal = c + x1 * y_raw + x2 * y_raw^2

        Raises:
            ValueError: If data is invalid or order is not 1 or 2
        """
        if len(setpoints) != len(measured_values):
            raise ValueError("setpoints and measured_values must have same length")

        if len(setpoints) < order + 1:
            raise ValueError(f"Need at least {order + 1} data points for order {order}")

        if order not in (1, 2):
            raise ValueError("order must be 1 (linear) or 2 (quadratic)")

        # Convert to numpy arrays
        setpoints = np.array(setpoints, dtype=float)
        measured = np.array(measured_values, dtype=float)

        # Fit polynomial: setpoint = coeffs[0] * measured^order + ... + coeffs[order]
        # np.polyfit returns coefficients in descending order of powers
        coeffs = np.polyfit(measured, setpoints, order)

        if order == 1:
            # Linear: setpoint = x1 * measured + c
            x1 = coeffs[0]
            c = coeffs[1]
            x2 = 0.0
        else:  # order == 2
            # Quadratic: setpoint = x2 * measured^2 + x1 * measured + c
            x2 = coeffs[0]
            x1 = coeffs[1]
            c = coeffs[2]

        return float(c), float(x1), float(x2)

    def calculate_fitness_score(
        self,
        setpoints: list[float],
        measured_values: list[float],
        c: float,
        x1: float,
        x2: float = 0.0,
    ) -> Tuple[float, float, float]:
        """Calculate fitness score (R²) and related metrics.

        Args:
            setpoints: Original setpoint data
            measured_values: Original measured data
            c: Constant term
            x1: Linear coefficient
            x2: Quadratic coefficient

        Returns:
            Tuple of (r_squared, rmse, normalized_rmse)
            r_squared: R² value (0-1, higher is better)
            rmse: Root mean square error
            normalized_rmse: RMSE as percentage of measurement range
        """
        setpoints_arr = np.array(setpoints, dtype=float)
        measured_arr = np.array(measured_values, dtype=float)

        # Calculate calibrated values
        calibrated = np.array(
            [self.calculate_calibrated(m, c, x1, x2) for m in measured_arr]
        )

        # Calculate residuals
        residuals = setpoints_arr - calibrated

        # Calculate R² (coefficient of determination)
        ss_res = np.sum(residuals ** 2)  # Sum of squares of residuals
        ss_tot = np.sum((setpoints_arr - np.mean(setpoints_arr)) ** 2)  # Total sum of squares
        r_squared = 1.0 - (ss_res / ss_tot) if ss_tot != 0 else 0.0

        # Calculate RMSE
        rmse = float(np.sqrt(np.mean(residuals ** 2)))

        # Calculate normalized RMSE (as percentage of range)
        measurement_range = np.max(setpoints_arr) - np.min(setpoints_arr)
        normalized_rmse = (rmse / measurement_range * 100) if measurement_range != 0 else 0.0

        return float(r_squared), rmse, float(normalized_rmse)

    def calculate_calibrated(
        self,
        raw_value: float,
        c: float,
        x1: float,
        x2: float = 0.0,
    ) -> float:
        """Calculate calibrated value using coefficients.

        Args:
            raw_value: Raw measured value from sensor
            c: Constant term
            x1: Linear coefficient
            x2: Quadratic coefficient (default 0 for linear model)

        Returns:
            Calibrated value: c + x1 * raw + x2 * raw^2
        """
        return c + x1 * raw_value + x2 * (raw_value ** 2)

    def print_calibration_summary(
        self,
        c: float,
        x1: float,
        x2: float,
        setpoints: list[float],
        measured_values: list[float],
    ) -> None:
        """Print calibration summary with statistics.

        Args:
            c: Constant term
            x1: Linear coefficient
            x2: Quadratic coefficient
            setpoints: Original setpoint data
            measured_values: Original measured data
        """
        # Calculate residuals
        calibrated = [
            self.calculate_calibrated(m, c, x1, x2) for m in measured_values
        ]
        residuals = np.array(setpoints) - np.array(calibrated)
        rmse = np.sqrt(np.mean(residuals ** 2))
        max_error = np.max(np.abs(residuals))

        # Calculate fitness score
        r_squared, rmse, normalized_rmse = self.calculate_fitness_score(
            setpoints, measured_values, c, x1, x2
        )

        # Determine fitness level
        if r_squared >= 0.99:
            fitness_level = "Excellent"
        elif r_squared >= 0.95:
            fitness_level = "Very Good"
        elif r_squared >= 0.90:
            fitness_level = "Good"
        elif r_squared >= 0.80:
            fitness_level = "Fair"
        else:
            fitness_level = "Poor"

        print("\n" + "=" * 60)
        print("CALIBRATION RESULTS")
        print("=" * 60)
        print(f"Constant (c):        {c:.6f}")
        print(f"Linear coeff (x1):   {x1:.6f}")
        print(f"Quadratic coeff (x2):{x2:.9f}")
        print(f"\nModel: y_cal = {c:.6f} + {x1:.6f} * y_raw + {x2:.9f} * y_raw^2")
        print(f"\nFitness Score:")
        print(f"  R² (fit quality):   {r_squared:.6f} ({fitness_level})")
        print(f"  RMSE:               {rmse:.6f}")
        print(f"  Normalized RMSE:    {normalized_rmse:.2f}%")
        print(f"  Max Error:          {max_error:.6f}")
        print(f"  Num Points:         {len(setpoints)}")
        print("=" * 60 + "\n")


def interactive_calibration():
    """Run interactive calibration session."""
    gen = CalibrationGenerator()

    print("\n" + "=" * 60)
    print("SENSOR CALIBRATION GENERATOR")
    print("=" * 60)

    # Get model type
    while True:
        order_input = input("\nSelect model (1=linear, 2=quadratic) [1]: ").strip()
        if not order_input:
            order = 1
        else:
            try:
                order = int(order_input)
                if order not in (1, 2):
                    print("Invalid choice. Please enter 1 or 2.")
                    continue
                break
            except ValueError:
                print("Invalid input. Please enter a number.")
                continue

    model_type = "Linear" if order == 1 else "Quadratic"
    print(f"\nUsing {model_type} model")

    # Get data points
    setpoints = []
    measured_values = []

    print(f"\nEnter calibration data points (at least {order + 1}):")
    print("Format: setpoint measured_value (space-separated)")
    print("Enter empty line when done\n")

    point_num = 1
    while True:
        user_input = input(f"Point {point_num}: ").strip()
        if not user_input:
            if len(setpoints) >= order + 1:
                break
            else:
                print(
                    f"Need at least {order + 1} points. You have {len(setpoints)}."
                )
                continue

        try:
            parts = user_input.split()
            if len(parts) != 2:
                print("Invalid format. Please enter: setpoint measured_value")
                continue

            setpoint = float(parts[0])
            measured = float(parts[1])

            setpoints.append(setpoint)
            measured_values.append(measured)
            point_num += 1
        except ValueError:
            print("Invalid input. Please enter two numbers.")
            continue

    # Fit calibration
    try:
        c, x1, x2 = gen.fit_data(setpoints, measured_values, order=order)
        gen.print_calibration_summary(c, x1, x2, setpoints, measured_values)

        # Print code snippets
        print("Python code for your application:")
        print("-" * 60)
        print(
            f"# Calibration coefficients (order={order})"
        )
        print(f"calibration_c = {c:.9f}")
        print(f"calibration_x1 = {x1:.9f}")
        print(f"calibration_x2 = {x2:.9f}")
        print(f"\n# Calibration formula")
        print(
            f"calibrated_value = {c:.9f} + {x1:.9f} * raw_value + {x2:.9f} * raw_value**2"
        )
        print("-" * 60)

        # Print C code snippet
        print("\nC code snippet:")
        print("-" * 60)
        print(
            f"float calibration_c = {c:.9f}f;"
        )
        print(f"float calibration_x1 = {x1:.9f}f;")
        print(f"float calibration_x2 = {x2:.9f}f;")
        print(f"\nfloat calibrated = calibration_c + calibration_x1 * raw + calibration_x2 * raw * raw;")
        print("-" * 60 + "\n")

    except ValueError as e:
        print(f"\nError: {e}")


if __name__ == "__main__":
    interactive_calibration()
