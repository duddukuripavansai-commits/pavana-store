from flask import (
    Flask, render_template, request,
    redirect, url_for, session
)
import sqlite3
from datetime import datetime

app = Flask(__name__, template_folder="views")
app.secret_key = "pavana-super-secret-key"   # change if you want
DB_NAME = "database.db"

ADMIN_USERNAME = "admin"
ADMIN_PASSWORD = "admin123"


# ---------- DB HELPERS ----------
def get_conn():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Ensure products table exists (columns were added via ALTER TABLE)."""
    conn = get_conn()
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
    conn.commit()
    conn.close()


def get_products():
    conn = get_conn()
    products = conn.execute("SELECT * FROM products").fetchall()
    conn.close()
    return products


# ---------- HOME (STORE) ----------
@app.route("/")
def home():
    q = request.args.get("q", "").strip()
    selected_category = request.args.get("category", "").strip()

    conn = get_conn()

    # dynamic categories
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


# ---------- CART (SESSION) ----------
def _find_in_list(lst, product_id):
    for idx, item in enumerate(lst):
        if int(item["id"]) == int(product_id):
            return idx
    return None


@app.route("/cart")
def cart():
    cart_items = session.get("cart", [])
    total = sum(float(item["price"]) * int(item["quantity"]) for item in cart_items) if cart_items else 0
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
            cart[idx]["quantity"] += 1

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


# ---------- WISHLIST (SESSION) ----------
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
        # only add if not already in wishlist
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
        # No items, go back to store
        return redirect(url_for("home"))

    total = sum(float(item["price"]) * int(item["quantity"]) for item in cart_items)

    if request.method == "POST":
        name = request.form.get("name")
        email = request.form.get("email")
        address = request.form.get("address")

        conn = get_conn()

        # create order
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO orders (customer_name, email, address, total_amount, created_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (name, email, address, total, datetime.now().isoformat(timespec="seconds"))
        )
        order_id = cur.lastrowid

        # create order_items
        for item in cart_items:
            cur.execute(
                "INSERT INTO order_items (order_id, product_id, quantity, price) "
                "VALUES (?, ?, ?, ?)",
                (order_id, item["id"], item["quantity"], item["price"])
            )

        conn.commit()
        conn.close()

        # clear cart
        session["cart"] = []

        return redirect(url_for("order_success", order_id=order_id))

    return render_template("checkout.html", cart_items=cart_items, total=total)


@app.route("/order_success/<int:order_id>")
def order_success(order_id):
    return render_template("order_success.html", order_id=order_id)


# ---------- RATINGS (simple) ----------
@app.route("/rate/<int:product_id>", methods=["POST"])
def rate_product(product_id):
    rating = request.form.get("rating")
    try:
        rating = float(rating)
    except (TypeError, ValueError):
        return redirect(url_for("home"))

    conn = get_conn()
    # For simplicity: overwrite rating (no averaging)
    conn.execute(
        "UPDATE products SET rating = ? WHERE id = ?",
        (rating, product_id)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("home"))


# ---------- ADMIN LOGIN / LOGOUT ----------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username")
        password = request.form.get("password")

        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            session["is_admin"] = True
            return redirect(url_for("admin_dashboard"))
        else:
            return render_template("login.html", error="Invalid username or password")

    return render_template("login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("is_admin", None)
    return redirect(url_for("home"))


def admin_required():
    return session.get("is_admin") is True


# ---------- ADMIN DASHBOARD (ANALYTICS) ----------
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

    # sales by category (for chart)
    sales_by_cat = conn.execute("""
        SELECT p.category AS category,
               SUM(oi.quantity * oi.price) AS total_sales
        FROM order_items oi
        JOIN products p ON p.id = oi.product_id
        GROUP BY p.category
    """).fetchall()

    conn.close()

    # Prepare data for chart
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


# ---------- ADMIN PRODUCT LIST ----------
@app.route("/admin/products")
def admin_products():
    if not admin_required():
        return redirect(url_for("admin_login"))

    products = get_products()
    return render_template("products.html", products=products)


# ---------- ADD PRODUCT ----------
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


# ---------- EDIT PRODUCT ----------
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


# ---------- DELETE PRODUCT ----------
@app.route("/admin/product/delete/<int:product_id>")
def delete_product(product_id):
    if not admin_required():
        return redirect(url_for("admin_login"))

    conn = get_conn()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()

    return redirect(url_for("admin_products"))


# ---------- MAIN ----------
if __name__ == "__main__":
    init_db()
    app.run(debug=True)
