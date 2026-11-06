from flask import Flask, render_template, jsonify, request
import pandas as pd
import numpy as np
import os

from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

DATA_FILE = os.path.join(
    BASE_DIR,
    "data",
    "business_analytics_sample_dataset.csv"
)

REQUIRED_COLUMNS = [
    "Order ID",
    "Invoice ID",
    "Order Date",
    "Customer Name",
    "Product Name",
    "Category",
    "Region",
    "Quantity",
    "Sales",
    "Cost",
    "Profit",
    "Payment Method"
]


# --------------------------------------------------
# CLEAN COLUMN NAMES
# --------------------------------------------------

def clean_columns(df):
    df.columns = (
        df.columns.astype(str)
        .str.replace("\ufeff", "", regex=False)
        .str.strip()
    )
    return df


# --------------------------------------------------
# LOAD DATASET
# --------------------------------------------------

def load_data():

    if not os.path.exists(DATA_FILE):
        raise FileNotFoundError(
            "Dataset CSV file not found. Please upload a dataset."
        )

    df = pd.read_csv(DATA_FILE, encoding="utf-8-sig")

    df = clean_columns(df)

    missing = [
        col for col in REQUIRED_COLUMNS
        if col not in df.columns
    ]

    if missing:
        raise ValueError(
            "Missing dataset columns: " + ", ".join(missing)
        )

    df["Order Date"] = pd.to_datetime(
        df["Order Date"],
        errors="coerce"
    )

    for col in ["Quantity", "Sales", "Cost", "Profit"]:
        df[col] = pd.to_numeric(
            df[col],
            errors="coerce"
        ).fillna(0)

    df = df.dropna(subset=["Order Date"])

    return df


# --------------------------------------------------
# APPLY DASHBOARD FILTERS
# --------------------------------------------------

def apply_filters(df):

    start_date = request.args.get("start_date")
    end_date = request.args.get("end_date")
    category = request.args.get("category")
    region = request.args.get("region")

    if start_date:
        start = pd.to_datetime(start_date, errors="coerce")

        if pd.notna(start):
            df = df[df["Order Date"] >= start]

    if end_date:
        end = pd.to_datetime(end_date, errors="coerce")

        if pd.notna(end):
            df = df[
                df["Order Date"] <
                end + pd.Timedelta(days=1)
            ]

    if category:
        df = df[
            df["Category"].astype(str) == category
        ]

    if region:
        df = df[
            df["Region"].astype(str) == region
        ]

    return df


# --------------------------------------------------
# CONVERT SERIES TO JSON
# --------------------------------------------------

def make_series(series):

    return {
        str(key): round(float(value), 2)
        for key, value in series.items()
    }


# --------------------------------------------------
# HOME PAGE
# --------------------------------------------------

@app.route("/")
def home():

    return render_template("index.html")


# --------------------------------------------------
# FILTER OPTIONS
# --------------------------------------------------

@app.route("/filter-options")
def filter_options():

    df = load_data()

    return jsonify({
        "categories": sorted(
            df["Category"].dropna().astype(str).unique().tolist()
        ),
        "regions": sorted(
            df["Region"].dropna().astype(str).unique().tolist()
        )
    })


# --------------------------------------------------
# DASHBOARD DATA
# --------------------------------------------------

@app.route("/dashboard-data")
def dashboard_data():

    df = apply_filters(load_data())

    monthly = (
        df.assign(
            Month=df["Order Date"].dt.to_period("M").astype(str)
        )
        .groupby("Month")["Sales"]
        .sum()
        .sort_index()
    )

    category_sales = (
        df.groupby("Category")["Sales"]
        .sum()
        .sort_values(ascending=False)
    )

    region_sales = (
        df.groupby("Region")["Sales"]
        .sum()
        .sort_values(ascending=False)
    )

    return jsonify({

        "total_sales": round(float(df["Sales"].sum()), 2),

        "total_profit": round(float(df["Profit"].sum()), 2),

        "total_orders": int(df["Order ID"].nunique()),

        "total_quantity": int(df["Quantity"].sum()),

        "monthly_sales": make_series(monthly),

        "category_sales": make_series(category_sales),

        "region_sales": make_series(region_sales)

    })


# --------------------------------------------------
# BUSINESS INSIGHTS
# --------------------------------------------------

@app.route("/insights-data")
def insights_data():

    df = apply_filters(load_data())

    if df.empty:

        return jsonify({

            "top_product": "No data",

            "highest_profit_category": "No data",

            "best_sales_month": "No data",

            "recommendations": [
                "No data available for selected filters."
            ]

        })

    product = (
        df.groupby("Product Name")["Quantity"]
        .sum()
        .sort_values(ascending=False)
    )

    category = (
        df.groupby("Category")["Profit"]
        .sum()
        .sort_values(ascending=False)
    )

    monthly = (
        df.assign(
            Month=df["Order Date"].dt.to_period("M").astype(str)
        )
        .groupby("Month")["Sales"]
        .sum()
        .sort_values(ascending=False)
    )

    recommendations = [

        "Focus on products with high sales quantity.",

        "Promote categories that generate higher profit.",

        "Review low-performing regions to improve sales."

    ]

    return jsonify({

        "top_product": str(product.index[0]),

        "highest_profit_category": str(category.index[0]),

        "best_sales_month": str(monthly.index[0]),

        "recommendations": recommendations

    })


# --------------------------------------------------
# FORECASTING PAGE
# --------------------------------------------------

@app.route("/forecasting")
def forecasting():

    return render_template("forecasting.html")


# --------------------------------------------------
# SALES FORECAST DATA
# --------------------------------------------------

@app.route("/forecast-data")
def forecast_data():

    df = load_data()

    monthly = (
        df.assign(
            Month=df["Order Date"].dt.to_period("M")
        )
        .groupby("Month")["Sales"]
        .sum()
        .sort_index()
    )

    if len(monthly) < 3:

        return jsonify({

            "error": "At least 3 months of sales data are needed for forecasting."

        }), 400

    values = monthly.values.astype(float)

    X = np.arange(len(values)).reshape(-1, 1)

    test_count = max(1, min(3, len(values) // 3))

    split = len(values) - test_count

    model = LinearRegression()

    model.fit(X[:split], values[:split])

    test_predictions = model.predict(X[split:])

    mae = mean_absolute_error(
        values[split:],
        test_predictions
    )

    rmse = np.sqrt(
        mean_squared_error(
            values[split:],
            test_predictions
        )
    )

    final_model = LinearRegression()

    final_model.fit(X, values)

    next_prediction = max(
        0,
        float(
            final_model.predict([[len(values)]])[0]
        )
    )

    actual_vs_predicted = []

    for i in range(split, len(values)):

        actual_vs_predicted.append({

            "month": str(monthly.index[i]),

            "actual": round(float(values[i]), 2),

            "predicted": round(
                float(test_predictions[i - split]), 2
            )

        })

    next_month = (
        monthly.index[-1] + 1
    ).strftime("%Y-%m")

    return jsonify({

        "next_month": next_month,

        "predicted_sales": round(next_prediction, 2),

        "mae": round(float(mae), 2),

        "rmse": round(float(rmse), 2),

        "actual_vs_predicted": actual_vs_predicted,

        "historical_months": [
            str(x) for x in monthly.index
        ],

        "historical_sales": [
            round(float(x), 2) for x in values
        ]

    })


# --------------------------------------------------
# INVENTORY PAGE
# --------------------------------------------------

@app.route("/inventory")
def inventory():

    return render_template("inventory.html")


# --------------------------------------------------
# INVENTORY DATA
# --------------------------------------------------

@app.route("/inventory-data")
def inventory_data():

    df = load_data()

    result = (
        df.groupby(
            ["Product Name", "Category"],
            as_index=False
        )
        .agg(
            total_quantity=("Quantity", "sum"),
            total_sales=("Sales", "sum")
        )
    )

    result["status"] = np.where(
        result["total_quantity"] <= 10,
        "Low Stock",
        "Available"
    )

    products = []

    for _, row in result.iterrows():

        products.append({

            "product_name": str(row["Product Name"]),

            "category": str(row["Category"]),

            "total_quantity": int(row["total_quantity"]),

            "total_sales": round(
                float(row["total_sales"]), 2
            ),

            "status": str(row["status"])

        })

    return jsonify({

        "total_products": int(
            result["Product Name"].nunique()
        ),

        "total_quantity": int(
            result["total_quantity"].sum()
        ),

        "total_sales": round(
            float(result["total_sales"].sum()), 2
        ),

        "products": products

    })


# --------------------------------------------------
# PAYMENTS PAGE
# --------------------------------------------------

@app.route("/payments")
def payments():

    return render_template("payments.html")


# --------------------------------------------------
# PAYMENT DATA
# --------------------------------------------------

@app.route("/payments-data")
def payments_data():

    df = load_data()

    result = (
        df.groupby("Payment Method")
        .agg(
            total_sales=("Sales", "sum"),
            total_orders=("Order ID", "nunique")
        )
        .reset_index()
    )

    payment_methods = {

        str(row["Payment Method"]): round(
            float(row["total_sales"]), 2
        )

        for _, row in result.iterrows()

    }

    return jsonify({

        "total_sales": round(
            float(df["Sales"].sum()), 2
        ),

        "total_orders": int(
            df["Order ID"].nunique()
        ),

        "payment_methods": payment_methods

    })


# --------------------------------------------------
# INVOICES PAGE
# --------------------------------------------------

@app.route("/invoices")
def invoices():

    return render_template("invoices.html")


# --------------------------------------------------
# INVOICE DATA
# --------------------------------------------------

@app.route("/invoices-data")
def invoices_data():

    df = load_data()

    result = (
        df.groupby(
            ["Invoice ID", "Order ID", "Customer Name"],
            as_index=False
        )
        .agg(
            total_amount=("Sales", "sum")
        )
    )

    invoices_list = []

    for _, row in result.iterrows():

        invoices_list.append({

            "invoice_id": str(row["Invoice ID"]),

            "order_id": str(row["Order ID"]),

            "customer_name": str(row["Customer Name"]),

            "invoice_amount": round(
                float(row["total_amount"]), 2
            )

        })

    return jsonify({

        "total_invoices": int(
            result["Invoice ID"].nunique()
        ),

        "total_amount": round(
            float(result["total_amount"].sum()), 2
        ),

        "invoices": invoices_list

    })


# --------------------------------------------------
# REPORTS PAGE
# --------------------------------------------------

@app.route("/reports")
def reports():

    return render_template("report.html")


# --------------------------------------------------
# MONTHLY REPORT DATA
# --------------------------------------------------

@app.route("/report-data")
def report_data():

    df = load_data()

    monthly = (
        df.assign(
            Month=df["Order Date"].dt.to_period("M").astype(str)
        )
        .groupby("Month")
        .agg(
            total_sales=("Sales", "sum"),
            total_profit=("Profit", "sum")
        )
        .reset_index()
        .sort_values("Month")
    )

    monthly_report = []

    for _, row in monthly.iterrows():

        monthly_report.append({

            "month": str(row["Month"]),

            "total_sales": round(
                float(row["total_sales"]), 2
            ),

            "total_profit": round(
                float(row["total_profit"]), 2
            )

        })

    return jsonify({

        "total_sales": round(
            float(df["Sales"].sum()), 2
        ),

        "total_profit": round(
            float(df["Profit"].sum()), 2
        ),

        "total_orders": int(
            df["Order ID"].nunique()
        ),

        "total_quantity": int(
            df["Quantity"].sum()
        ),

        "monthly_report": monthly_report

    })


# --------------------------------------------------
# DATASET UPLOAD PAGE
# --------------------------------------------------

@app.route("/upload", methods=["GET", "POST"])
def upload():

    if request.method == "POST":

        file = request.files.get("file")

        if not file or not file.filename:

            return render_template(
                "upload.html",
                error="Please select a file."
            )

        extension = os.path.splitext(
            file.filename
        )[1].lower()

        try:

            # Read CSV or Excel file
            if extension == ".csv":

                uploaded_df = pd.read_csv(
                    file,
                    encoding="utf-8-sig"
                )

            elif extension in [".xlsx", ".xls"]:

                uploaded_df = pd.read_excel(file)

            else:

                return render_template(
                    "upload.html",
                    error="Only CSV and Excel files are supported."
                )

            # Clean column names
            uploaded_df = clean_columns(uploaded_df)

            # Check required columns
            missing = [
                col for col in REQUIRED_COLUMNS
                if col not in uploaded_df.columns
            ]

            if missing:

                return render_template(
                    "upload.html",
                    error="Missing columns: " + ", ".join(missing)
                )

            # Check whether dataset contains records
            if uploaded_df.empty:

                return render_template(
                    "upload.html",
                    error="Uploaded dataset is empty."
                )

            # Validate date column
            uploaded_df["Order Date"] = pd.to_datetime(
                uploaded_df["Order Date"],
                errors="coerce"
            )

            if uploaded_df["Order Date"].isna().all():

                return render_template(
                    "upload.html",
                    error="Invalid Order Date values."
                )

            # Validate numeric columns
            for col in ["Quantity", "Sales", "Cost", "Profit"]:

                uploaded_df[col] = pd.to_numeric(
                    uploaded_df[col],
                    errors="coerce"
                )

            if uploaded_df[
                ["Quantity", "Sales", "Cost", "Profit"]
            ].isna().all().any():

                return render_template(
                    "upload.html",
                    error="Some numeric columns contain invalid data."
                )

            # Create data folder
            os.makedirs(
                os.path.dirname(DATA_FILE),
                exist_ok=True
            )

            # Save uploaded dataset
            uploaded_df.to_csv(
                DATA_FILE,
                index=False
            )

            return render_template(
                "upload.html",
                message="Dataset uploaded successfully!"
            )

        except Exception as e:

            return render_template(
                "upload.html",
                error="Upload failed: " + str(e)
            )

    return render_template("upload.html")


# --------------------------------------------------
# RUN FLASK APPLICATION
# --------------------------------------------------

if __name__ == "__main__":

    app.run(
        debug=True
    )