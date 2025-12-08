from flask import (
    Flask, render_template, request,
    redirect, url_for, session, flash
)
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3
from datetime import datetime

# Flask app, templates in "views"
app = Flask(__name__, template_folder="views")
app.secret_key = "pavana-super-secret-key"
DB_NAME = "database.db"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


# ---------- DB HELPERS ----------
def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Create all needed tables if they don't exist."""
    conn = get_conn()

    # Products table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            description TEXT,
            price REAL NOT NULL,
            category TEXT,
            image_url TEXT,
            rating REAL
        );
    """)

    # Users table (for login/signup)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            address TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
    """)

    # Orders table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_name TEXT NOT NULL,
            email TEXT NOT NULL,
            address TEXT,
            total_amount REAL NOT NULL,
            created_at TEXT NOT NULL
        );
    """)

    # Order items table
    conn.execute("""
        CREATE TABLE IF NOT EXISTS order_items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            order_id INTEGER NOT NULL,
            product_id INTEGER NOT NULL,
            quantity INTEGER NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY (order_id) REFERENCES orders(id),
            FOREIGN KEY (product_id) REFERENCES products(id)
        );
    """)

    conn.commit()
    conn.close()

def get_products():
    conn = get_conn()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return products


def get_current_user():
    user_email = session.get("user_email")
    if not user_email:
        return None
    conn = get_conn()
    user = conn.execute(
        "SELECT * FROM users WHERE email = ?",
        (user_email,)
    ).fetchone()
    conn.close()
    return user


def _find_in_list(lst, product_id):
    for idx, item in enumerate(lst):
        if int(item["id"]) == int(product_id):
            return idx
    return None


# ---------- HOME (STORE) ----------
@app.route("/")
def home():
    q = request.args.get("q", "").strip()
    selected_category = request.args.get("category", "").strip()

    conn = get_conn()

    categories = conn.execute(
        "SELECT DISTINCT category FROM products "
        "WHERE category IS NOT NULL AND TRIM(category) != ''"
    ).fetchall()

    sql = "SELECT * FROM products WHERE 1=1"
    params = []

    if q:
        sql += " AND (name LIKE ? OR description LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])

    if selected_category:
        sql += " AND category = ?"
        params.append(selected_category)

    products = conn.execute(sql, params).fetchall()
    conn.close()

    return render_template(
        "index.html",
        products=products,
        q=q,
        categories=categories,
        selected_category=selected_category
    )


# ---------- SIGNUP / LOGIN / LOGOUT ----------
@app.route("/signup", methods=["GET", "POST"])
def signup():
    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        password = request.form.get("password")
        confirm = request.form.get("confirm")

        if not name or not email or not password:
            flash("All fields are required.", "error")
            return redirect(url_for("signup"))

        if password != confirm:
            flash("Passwords do not match.", "error")
            return redirect(url_for("signup"))

        password_hash = generate_password_hash(password)

        conn = get_conn()
        try:
            conn.execute(
                "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                (name, email, password_hash),
            )
            conn.commit()
        except sqlite3.IntegrityError:
            flash("An account with that email already exists.", "error")
            conn.close()
            return redirect(url_for("signup"))

        conn.close()
        flash("Account created successfully. Please log in.", "success")
        return redirect(url_for("login_user"))

    return render_template("signup.html")


@app.route("/login", methods=["GET", "POST"])
def login_user():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = get_conn()
        user = conn.execute(
            "SELECT * FROM users WHERE email = ?",
            (email,)
        ).fetchone()
        conn.close()

        if user is None or not check_password_hash(user["password_hash"], password):
            flash("Invalid email or password.", "error")
            return redirect(url_for("login_user"))

        session["user_email"] = user["email"]
        session["user_name"] = user["name"]

        flash("Logged in successfully.", "success")
        return redirect(url_for("home"))

    return render_template("login.html")


@app.route("/logout")
def logout_user():
    session.pop("user_email", None)
    session.pop("user_name", None)
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))


# ---------- MY ORDERS ----------
@app.route("/my_orders")
def my_orders():
    if "user_email" not in session:
        flash("Please log in to view your orders.", "error")
        return redirect(url_for("login_user"))

    user_email = session["user_email"]

    conn = get_conn()
    orders = conn.execute(
        "SELECT * FROM orders WHERE email = ? ORDER BY created_at DESC",
        (user_email,),
    ).fetchall()
    conn.close()

    return render_template("my_orders.html", orders=orders)


# ---------- CART ----------
@app.route("/cart")
def cart():
    cart_items = session.get("cart", [])
    total = sum(
        float(item["price"]) * int(item["quantity"])
        for item in cart_items
    ) if cart_items else 0.0

    return render_template("cart.html", cart_items=cart_items, total=total)


@app.route("/add_to_cart/<int:product_id>")
def add_to_cart(product_id):
    conn = get_conn()
    product = conn.execute(
        "SELECT * FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    conn.close()

    if product:
        cart = session.get("cart", [])
        idx = _find_in_list(cart, product_id)
        if idx is None:
            cart.append({
                "id": product["id"],
                "name": product["name"],
                "description": product["description"],
                "price": float(product["price"]),
                "category": product["category"],
                "image_url": product["image_url"],
                "quantity": 1
            })
        else:
            cart[idx]["quantity"] = int(cart[idx]["quantity"]) + 1

        session["cart"] = cart

    return redirect(url_for("cart"))


@app.route("/remove_from_cart/<int:product_id>")
def remove_from_cart(product_id):
    cart = session.get("cart", [])
    idx = _find_in_list(cart, product_id)
    if idx is not None:
        del cart[idx]
    session["cart"] = cart
    return redirect(url_for("cart"))

@app.route("/cart/increase/<int:product_id>")
def cart_increase(product_id):
    cart = session.get("cart", [])
    idx = _find_in_list(cart, product_id)
    if idx is not None:
        cart[idx]["quantity"] += 1
    session["cart"] = cart
    return redirect(url_for("cart"))

@app.route("/cart/decrease/<int:product_id>")
def cart_decrease(product_id):
    cart = session.get("cart", [])
    idx = _find_in_list(cart, product_id)
    if idx is not None:
        if cart[idx]["quantity"] > 1:
            cart[idx]["quantity"] -= 1
        else:
            del cart[idx]
    session["cart"] = cart
    return redirect(url_for("cart"))



# ---------- WISHLIST ----------
@app.route("/wishlist")
def wishlist():
    wishlist_items = session.get("wishlist", [])
    return render_template("wishlist.html", wishlist_items=wishlist_items)


@app.route("/add_to_wishlist/<int:product_id>")
def add_to_wishlist(product_id):
    conn = get_conn()
    product = conn.execute(
        "SELECT * FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    conn.close()

    if product:
        wishlist = session.get("wishlist", [])
        if _find_in_list(wishlist, product_id) is None:
            wishlist.append({
                "id": product["id"],
                "name": product["name"],
                "description": product["description"],
                "price": float(product["price"]),
                "category": product["category"],
                "image_url": product["image_url"],
            })
            session["wishlist"] = wishlist

    return redirect(url_for("wishlist"))


# ---------- CHECKOUT ----------
@app.route("/checkout", methods=["GET", "POST"])
def checkout():
    cart_items = session.get("cart", [])
    if not cart_items:
        return redirect(url_for("home"))

    total = sum(
        float(item["price"]) * int(item["quantity"])
        for item in cart_items
    )

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        address = request.form.get("address")

        conn = get_conn()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (customer_name, email, address, total_amount, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, email, address, total, datetime.now().isoformat(timespec="seconds"))
        )
        order_id = cur.lastrowid

        for item in cart_items:
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, price) "
                "VALUES (?, ?, ?, ?)",
                (order_id, item["id"], item["quantity"], item["price"])
            )

        conn.commit()
        conn.close()

        session["cart"] = []

        return redirect(url_for("order_success", order_id=order_id))

    return render_template("checkout.html", cart_items=cart_items, total=total)


@app.route("/order_success/<int:order_id>")
def order_success(order_id):
    return render_template("order_success.html", order_id=order_id)


# ---------- RATINGS ----------
@app.route("/rate/<int:product_id>", methods=["POST"])
def rate_product(product_id):
    rating = request.form.get("rating")
    try:
        rating = float(rating)
    except (TypeError, ValueError):
        return redirect(url_for("home"))

    conn = get_conn()
    conn.execute(
        "UPDATE products SET rating = ? WHERE id = ?",
        (rating, product_id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


# ---------- ADMIN ----------
def admin_required():
    return session.get("is_admin") is True


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    error = None
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            error = "Invalid username or password"

    return render_template("admin_login.html", error=error)


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("home"))


@app.route("/admin/dashboard")
def admin_dashboard():
    if not admin_required():
        return redirect(url_for("admin_login"))

    conn = get_conn()

    total_products = conn.execute(
        "SELECT COUNT(*) AS c FROM products"
    ).fetchone()["c"]

    total_value_row = conn.execute(
        "SELECT SUM(price) AS s FROM products"
    ).fetchone()
    total_value = total_value_row["s"] if total_value_row["s"] is not None else 0

    total_orders = conn.execute(
        "SELECT COUNT(*) AS c FROM orders"
    ).fetchone()["c"]

    total_revenue_row = conn.execute(
        "SELECT SUM(total_amount) AS s FROM orders"
    ).fetchone()
    total_revenue = total_revenue_row["s"] if total_revenue_row["s"] is not None else 0

    sales_by_cat = conn.execute("""
        SELECT p.category AS category,
               SUM(oi.quantity * oi.price) AS total_sales
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        GROUP BY p.category
    """).fetchall()

    conn.close()

    chart_labels = [row["category"] or "Uncategorized" for row in sales_by_cat]
    chart_values = [row["total_sales"] for row in sales_by_cat]

    return render_template(
        "dashboard.html",
        total_products=total_products,
        total_value=total_value,
        total_orders=total_orders,
        total_revenue=total_revenue,
        chart_labels=chart_labels,
        chart_values=chart_values
    )


@app.route("/admin/products")
def admin_products():
    if not admin_required():
        return redirect(url_for("admin_login"))

    products = get_products()
    return render_template("products.html", products=products)


@app.route("/admin/product/add", methods=["GET", "POST"])
def add_product():
    if not admin_required():
        return redirect(url_for("admin_login"))

    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        price = request.form.get("price")
        category = request.form.get("category")
        image_url = request.form.get("image_url")

        conn = get_conn()
        conn.execute(
            "INSERT INTO products (name, description, price, category, image_url) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, description, price, category, image_url),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("admin_products"))

    return render_template("product.html")


@app.route("/admin/product/edit/<int:product_id>", methods=["GET", "POST"])
def edit_product(product_id):
    if not admin_required():
        return redirect(url_for("admin_login"))

    conn = get_conn()

    if request.method == "POST":
        name = request.form.get("name")
        description = request.form.get("description")
        price = request.form.get("price")
        category = request.form.get("category")
        image_url = request.form.get("image_url")

        conn.execute(
            "UPDATE products "
            "SET name = ?, description = ?, price = ?, category = ?, image_url = ? "
            "WHERE id = ?",
            (name, description, price, category, image_url, product_id),
        )
        conn.commit()
        conn.close()
        return redirect(url_for("admin_products"))

    product = conn.execute(
        "SELECT * FROM products WHERE id = ?",
        (product_id,),
    ).fetchone()
    conn.close()

    if not product:
        return "Product not found", 404

    return render_template("edit_product.html", product=product)


@app.route("/admin/product/delete/<int:product_id>")
def delete_product(product_id):
    if not admin_required():
        return redirect(url_for("admin_login"))

    conn = get_conn()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_products"))


# ---------- MAIN ---------

# Always initialize DB when the app module is imported
with app.app_context():
    init_db()

if __name__ == "__main__":
    app.run(debug=True)
