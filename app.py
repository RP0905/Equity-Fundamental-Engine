from flask import Flask, render_template, request
from services.yf_services import get_stock_data
from analysis.fundamentals import get_fundamentals
from analysis.technicals import get_technicals
from analysis.old_engine import get_old_data

app = Flask(__name__)

@app.route("/", methods=["GET", "POST"])
def index():
    data = None

    if request.method == "POST":
        ticker = request.form["ticker"]

        try:
            stock_data = get_stock_data(ticker)

            fundamentals = get_fundamentals(stock_data)
            technicals = get_technicals(stock_data["history"])
            old_data = get_old_data(stock_data, ticker)

            data = {
                "fundamentals": fundamentals,
                "technicals": technicals,
                "company_info": old_data["company_info"],
                "ratios": old_data["ratios"],
                "tables": old_data["tables"]
            }

        except Exception as e:
            data = {"error": str(e)}

    return render_template("index.html", data=data)


if __name__ == "__main__":
    app.run(debug=True)