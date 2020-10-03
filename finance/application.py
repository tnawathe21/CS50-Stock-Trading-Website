import os

from cs50 import SQL
from flask import Flask, flash, jsonify, redirect, render_template, request, session
from flask_session import Session
from tempfile import mkdtemp
from werkzeug.exceptions import default_exceptions, HTTPException, InternalServerError
from werkzeug.security import check_password_hash, generate_password_hash

from helpers import apology, login_required, lookup, usd

# Configure application
app = Flask(__name__)

# Ensure templates are auto-reloaded
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Ensure responses aren't cached
@app.after_request
def after_request(response):
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Expires"] = 0
    response.headers["Pragma"] = "no-cache"
    return response

# Custom filter
app.jinja_env.filters["usd"] = usd

# Configure session to use filesystem (instead of signed cookies)
app.config["SESSION_FILE_DIR"] = mkdtemp()
app.config["SESSION_PERMANENT"] = False
app.config["SESSION_TYPE"] = "filesystem"
Session(app)

# Configure CS50 Library to use SQLite database
db = SQL("sqlite:///finance.db")

# Make sure API key is set
if not os.environ.get("API_KEY"):
    raise RuntimeError("API_KEY not set")


@app.route("/")
@login_required
def index():
    """Show portfolio of stocks"""

    index = db.execute("SELECT * FROM portfolio WHERE user_id = :userid AND shares > 0", userid = session["user_id"])
    cash = db.execute("SELECT cash FROM users WHERE id = :userid", userid = session["user_id"])

    stockTotal = 0

    for row in index:
        row.pop("user_id")
        stock = lookup(row["symbol"])
        row["price"] = stock["price"] # Update stock price to latest value
        row["total"] = row["shares"] * row["price"] # Update total price based on latest stock price
        stockTotal += row["total"] # Calculate total stock value

    return render_template("index.html", index=index, cash=usd(cash[0]["cash"]), total=usd(stockTotal + cash[0]["cash"]))


@app.route("/buy", methods=["GET", "POST"])
@login_required
def buy():
    """Buy shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        stock = lookup(request.form.get("symbol"))

        # Exit if stock symbol is invalid
        if stock is None:
            return apology("invalid stock symbol", 403)

        shares = int(request.form.get("shares"))

        # Exit if number of shares is invalid
        if shares < 0:
            return apology("must provide positive number", 403)

        # Find out how much cash user has
        cash = db.execute("SELECT cash FROM users WHERE id = :userid", userid=session["user_id"])

        # Exit if user does not have enough money to buy the shares
        total = (stock["price"] * shares)
        if cash[0]["cash"] < total:
            return apology("not enough money to make purchase", 403)

        # Subtract cash
        db.execute("UPDATE users SET cash = :cash WHERE id = :userid", cash=cash[0]["cash"]-total, userid=session["user_id"])

        # Add transaction to history
        db.execute("INSERT INTO history (user_id, symbol, shares, price) VALUES (:userid, :symbol, :shares, :price)",
        userid=session["user_id"], symbol=stock["symbol"], shares=shares, price=stock["price"])

        # Update index (homepage)

        # Check if user has bought this stock before
        check = db.execute("SELECT symbol FROM portfolio WHERE user_id = :userid AND symbol = :symbol",
        userid=session["user_id"], symbol=stock["symbol"])

        print(check)

        if check == []: # Add a new row into index if they haven't bought this stock before
            db.execute("INSERT INTO portfolio (user_id, symbol, name, shares, price, total) VALUES (:userid, :symbol, :name, :shares, :price, :total)",
            userid=session["user_id"], symbol=stock["symbol"], name=stock["name"], shares=shares, price=stock["price"], total=total)

        else:
            # Find out how many shares user already owns
            oldIndex = db.execute("SELECT shares FROM portfolio WHERE user_id = :userid AND symbol = :symbol",
            userid=session["user_id"], symbol=stock["symbol"])

            print(oldIndex)

            # Compute new share and price total
            shares = shares + oldIndex[0]["shares"]
            total = (stock["price"] * shares)

            # Update their stock portfolio
            db.execute("UPDATE portfolio SET shares=:shares, price=:price, total=:total WHERE user_id=:userid AND symbol=:symbol",
            shares=shares, price=stock["price"], total=total, userid=session["user_id"], symbol=stock["symbol"])

        return redirect("/")

    else:
        return render_template("buy.html")

@app.route("/history")
@login_required
def history():
    """Show history of transactions"""

    history = db.execute("SELECT * FROM history WHERE user_id = :userid ORDER BY transacted DESC", userid = session["user_id"])

    for row in history:
        row.pop("user_id")

    return render_template("history.html", history=history)


@app.route("/login", methods=["GET", "POST"])
def login():
    """Log user in"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Query database for username
        rows = db.execute("SELECT * FROM users WHERE username = :username",
                          username=request.form.get("username"))

        # Ensure username exists and password is correct
        if len(rows) != 1 or not check_password_hash(rows[0]["hash"], request.form.get("password")):
            return apology("invalid username and/or password", 403)

        # Remember which user has logged in
        session["user_id"] = rows[0]["id"]

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("login.html")


@app.route("/logout")
def logout():
    """Log user out"""

    # Forget any user_id
    session.clear()

    # Redirect user to login form
    return redirect("/")


@app.route("/quote", methods=["GET", "POST"])
@login_required
def quote():
    """Get stock quote."""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":
        quote = lookup(request.form.get("symbol"))

        # Exit if stock symbol is invalid
        if quote is None:
            return apology("invalid stock symbol", 403)

        quote["price"] = usd(quote["price"])
        return render_template("quoted.html", quote=quote)

    else:
        return render_template("quote.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    """Register user"""

    # Forget any user_id
    session.clear()

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        # Ensure username was submitted
        if not request.form.get("username"):
            return apology("must provide username", 403)

        # Ensure username doesn't already exist
        if request.form.get("username") == db.execute("SELECT * FROM users WHERE username = :username", username=request.form.get("username")):
            return apology("username already exists", 403)

        # Ensure password was submitted
        elif not request.form.get("password"):
            return apology("must provide password", 403)

        # Ensure confirmation password was submitted
        elif not request.form.get("confirmation"):
            return apology("must confirm password", 403)

        # Ensure password and confirmation match
        elif request.form.get("password") != request.form.get("confirmation"):
            return apology("passwords must match", 403)

        # Add user to database and remember which user has logged in
        session["user_ed"] = db.execute("INSERT INTO users (username, hash) VALUES (:username, :password);", username=request.form.get("username"), password=generate_password_hash(request.form.get("password")))

        # Redirect user to home page
        return redirect("/")

    # User reached route via GET (as by clicking a link or via redirect)
    else:
        return render_template("register.html")


@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    """Sell shares of stock"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        stock = lookup(request.form.get("symbol"))
        shares = int(request.form.get("shares")) * -1

        # Check invalid input - 1) did they select a symbol? 2) do they own that stock? 3) are they accidentally selling more than they own?
        if stock is None:
            return apology("you must choose a stock", 403)

        check = db.execute("SELECT * FROM portfolio WHERE user_id=:userid AND symbol=:symbol", userid=session["user_id"], symbol=stock["symbol"])
        if check is None:
            return apology("you do not own this stock", 403)

        oldShares = db.execute("SELECT shares FROM portfolio WHERE user_id=:userid AND symbol=:symbol", userid=session["user_id"], symbol=stock["symbol"])
        if int(oldShares[0]["shares"]) < (shares * -1):
            return apology(f"you do not own {shares * -1} shares", 403)

        # Add transaction to history
        db.execute("INSERT INTO history (user_id, symbol, shares, price) VALUES (:userid, :symbol, :shares, :price)",
        userid=session["user_id"], symbol=stock["symbol"], shares=shares, price=stock["price"])

        # Update cash balance
        cash = db.execute("SELECT cash FROM users where id = :userid", userid=session["user_id"])
        cost = (shares * -1) * stock["price"]
        db.execute("UPDATE users SET cash = :cash WHERE id = :userid", cash=cash[0]["cash"] + cost, userid=session["user_id"])

        # Update stock portfolio
        shares = oldShares[0]["shares"]+shares
        db.execute("UPDATE portfolio SET shares=:shares, price=:price, total=:total WHERE user_id=:userid AND symbol=:symbol",
        shares=shares, price=stock["price"], total=shares * stock["price"], userid=session["user_id"], symbol=stock["symbol"])

        return redirect("/")

    else:

        # For the drop-down menu
        dictionary = db.execute("SELECT symbol FROM portfolio WHERE user_id=:userid", userid=session["user_id"])

        return render_template("sell.html", dictionary=dictionary)

@app.route("/cash", methods=["GET", "POST"])
@login_required
def cash():
    """Load more cash onto user's account"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":

        if float(request.form.get("amount")) <= 0:
            return apology("Invalid amount entered", 403)

        oldAmount = db.execute("SELECT cash FROM users WHERE id = :userid", userid=session["user_id"])
        db.execute("UPDATE users SET cash = :cash WHERE id = :userid", cash = float(oldAmount[0]["cash"]) +
        float(request.form.get("amount")), userid = session["user_id"])

        return redirect("/")

    else:
        return render_template("cash.html")

@app.route("/change", methods=["GET", "POST"])
@login_required
def change():
    """Change password of user"""

    # User reached route via POST (as by submitting a form via POST)
    if request.method == "POST":


        # Error checking
        if not request.form.get("oldpass") or not request.form.get("password") or not request.form.get("confirm"):
            return apology("Missing one or more fields", 403)

        password = db.execute("SELECT hash FROM users where id=:userid", userid=session["user_id"])
        if not check_password_hash(password[0]["hash"], request.form.get("oldpass")):
            return apology("Incorrect password", 403)

        if request.form.get("password") != request.form.get("confirm"):
            return apology("Passwords must match", 403)

        db.execute("UPDATE users SET hash = :password WHERE id=:userid", password=generate_password_hash(request.form.get("password")),
        userid=session["user_id"])

        return apology("TODO", 400)

    else:
        return render_template("change.html")

def errorhandler(e):
    """Handle error"""
    if not isinstance(e, HTTPException):
        e = InternalServerError()
    return apology(e.name, e.code)


# Listen for errors
for code in default_exceptions:
    app.errorhandler(code)(errorhandler)
