import os
import sys
import secrets
from datetime import datetime
from decimal import Decimal, InvalidOperation
from functools import wraps

import click
from flask import Flask, render_template, request, redirect, url_for, flash, session, abort
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
app = Flask(__name__)
app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY") or secrets.token_hex(32)
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///" + os.path.join(BASE_DIR, "store.db"))
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 3 * 1024 * 1024
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["REMEMBER_COOKIE_HTTPONLY"] = True
app.config["STORE_NAME"] = os.environ.get("STORE_NAME", "Nanu Bhai Store")
app.config["CURRENCY"] = os.environ.get("CURRENCY", "INR")

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "login"
login_manager.login_message = "Please log in to continue."
csrf = CSRFProtect(app)

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp", "gif"}

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False, nullable=False)
    is_active_account = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    orders = db.relationship("Order", backref="customer", lazy=True)

    @property
    def is_active(self):
        return self.is_active_account

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), unique=True, nullable=False)
    slug = db.Column(db.String(100), unique=True, nullable=False)

class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(160), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Integer, nullable=False)  # INR paise-free whole rupees for starter
    compare_price = db.Column(db.Integer, nullable=True)
    stock = db.Column(db.Integer, default=0, nullable=False)
    sku = db.Column(db.String(80), unique=True, nullable=True)
    image_url = db.Column(db.String(500), default="")
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=True)
    is_featured = db.Column(db.Boolean, default=False, nullable=False)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    category = db.relationship("Category", backref="products")

class Order(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    full_name = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30), nullable=False)
    address = db.Column(db.String(300), nullable=False)
    city = db.Column(db.String(80), nullable=False)
    state = db.Column(db.String(80), nullable=False)
    pincode = db.Column(db.String(12), nullable=False)
    subtotal = db.Column(db.Integer, nullable=False)
    shipping = db.Column(db.Integer, nullable=False, default=0)
    total = db.Column(db.Integer, nullable=False)
    payment_method = db.Column(db.String(30), default="COD", nullable=False)
    payment_status = db.Column(db.String(30), default="Pending", nullable=False)
    status = db.Column(db.String(30), default="Placed", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    items = db.relationship("OrderItem", backref="order", cascade="all, delete-orphan", lazy=True)

class OrderItem(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=True)
    product_name = db.Column(db.String(160), nullable=False)  # price/name snapshot
    unit_price = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)

@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))

@app.context_processor
def inject_globals():
    cart = session.get("cart", {})
    cart_count = sum(int(q) for q in cart.values() if str(q).isdigit())
    return {"store_name": app.config["STORE_NAME"], "currency": "₹", "cart_count": cart_count}

def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(*args, **kwargs):
        if not current_user.is_admin:
            abort(403)
        return fn(*args, **kwargs)
    return wrapper

def parse_int(value, minimum=None, maximum=None):
    try:
        n = int(value)
    except (TypeError, ValueError):
        raise ValueError("Please enter a valid whole number.")
    if minimum is not None and n < minimum:
        raise ValueError(f"Value must be at least {minimum}.")
    if maximum is not None and n > maximum:
        raise ValueError(f"Value must be no more than {maximum}.")
    return n

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def home():
    featured = Product.query.filter_by(is_active=True, is_featured=True).order_by(Product.created_at.desc()).limit(8).all()
    latest = Product.query.filter_by(is_active=True).order_by(Product.created_at.desc()).limit(12).all()
    categories = Category.query.order_by(Category.name.asc()).all()
    return render_template("home.html", featured=featured, latest=latest, categories=categories)

@app.route("/products")
def products():
    q = request.args.get("q", "").strip()[:100]
    category_id = request.args.get("category", "").strip()
    sort = request.args.get("sort", "newest")
    query = Product.query.filter_by(is_active=True)
    if q:
        query = query.filter(Product.name.ilike(f"%{q}%"))
    if category_id.isdigit():
        query = query.filter_by(category_id=int(category_id))
    if sort == "price_low":
        query = query.order_by(Product.price.asc())
    elif sort == "price_high":
        query = query.order_by(Product.price.desc())
    elif sort == "name":
        query = query.order_by(Product.name.asc())
    else:
        query = query.order_by(Product.created_at.desc())
    items = query.all()
    return render_template("products.html", products=items, categories=Category.query.all(), q=q, selected_category=category_id, sort=sort)

@app.route("/product/<int:product_id>")
def product_detail(product_id):
    product = Product.query.filter_by(id=product_id, is_active=True).first_or_404()
    related = Product.query.filter(Product.is_active.is_(True), Product.id != product.id).limit(4).all()
    return render_template("product_detail.html", product=product, related=related)

@app.route("/register", methods=["GET", "POST"])
def register():
    if current_user.is_authenticated:
        return redirect(url_for("home"))
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:100]
        email = request.form.get("email", "").strip().lower()[:160]
        password = request.form.get("password", "")
        confirm = request.form.get("confirm_password", "")
        if len(name) < 2 or "@" not in email:
            flash("Please enter a valid name and email.", "error")
        elif len(password) < 8:
            flash("Password must be at least 8 characters.", "error")
        elif password != confirm:
            flash("Passwords do not match.", "error")
        elif User.query.filter_by(email=email).first():
            flash("An account with this email already exists.", "error")
        else:
            user = User(name=name, email=email)
            user.set_password(password)
            db.session.add(user)
            db.session.commit()
            login_user(user)
            flash("Account created successfully.", "success")
            return redirect(url_for("home"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if current_user.is_authenticated:
        return redirect(url_for("admin_dashboard" if current_user.is_admin else "dashboard"))
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and user.is_active_account and user.check_password(password):
            login_user(user, remember=bool(request.form.get("remember")))
            flash("Welcome back!", "success")
            next_url = request.args.get("next", "")
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("admin_dashboard" if user.is_admin else "dashboard"))
        flash("Email or password is incorrect.", "error")
    return render_template("login.html")

@app.route("/logout", methods=["POST"])
@login_required
def logout():
    logout_user()
    flash("You have been logged out.", "success")
    return redirect(url_for("home"))

@app.route("/cart")
def cart():
    cart_data = session.get("cart", {})
    rows, subtotal = [], 0
    for product_id, quantity in cart_data.items():
        if not str(product_id).isdigit() or not str(quantity).isdigit():
            continue
        product = Product.query.filter_by(id=int(product_id), is_active=True).first()
        quantity = int(quantity)
        if product and quantity > 0:
            line_total = product.price * quantity
            subtotal += line_total
            rows.append({"product": product, "quantity": quantity, "line_total": line_total})
    return render_template("cart.html", rows=rows, subtotal=subtotal)

@app.route("/cart/add/<int:product_id>", methods=["POST"])
def cart_add(product_id):
    product = Product.query.filter_by(id=product_id, is_active=True).first_or_404()
    try:
        quantity = parse_int(request.form.get("quantity", "1"), 1, 20)
    except ValueError as e:
        flash(str(e), "error")
        return redirect(url_for("product_detail", product_id=product_id))
    if product.stock < quantity:
        flash("Not enough stock available.", "error")
        return redirect(url_for("product_detail", product_id=product_id))
    cart_data = session.get("cart", {})
    current_qty = int(cart_data.get(str(product_id), 0))
    if current_qty + quantity > product.stock:
        flash("Cart quantity would exceed available stock.", "error")
        return redirect(url_for("product_detail", product_id=product_id))
    cart_data[str(product_id)] = current_qty + quantity
    session["cart"] = cart_data
    flash("Added to cart.", "success")
    return redirect(request.form.get("next") or url_for("cart"))

@app.route("/cart/update", methods=["POST"])
def cart_update():
    cart_data = session.get("cart", {})
    for key in list(cart_data.keys()):
        try:
            qty = parse_int(request.form.get(f"quantity_{key}", cart_data[key]), 0, 20)
        except ValueError:
            continue
        product = db.session.get(Product, int(key)) if key.isdigit() else None
        if qty == 0 or not product or not product.is_active:
            cart_data.pop(key, None)
        else:
            cart_data[key] = min(qty, product.stock)
    session["cart"] = cart_data
    flash("Cart updated.", "success")
    return redirect(url_for("cart"))

@app.route("/checkout", methods=["GET", "POST"])
@login_required
def checkout():
    cart_data = session.get("cart", {})
    if not cart_data:
        flash("Your cart is empty.", "error")
        return redirect(url_for("products"))
    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()[:120]
        phone = request.form.get("phone", "").strip()[:30]
        address = request.form.get("address", "").strip()[:300]
        city = request.form.get("city", "").strip()[:80]
        state = request.form.get("state", "").strip()[:80]
        pincode = request.form.get("pincode", "").strip()[:12]
        if not all([full_name, phone, address, city, state, pincode]):
            flash("Please complete all shipping fields.", "error")
            return render_template("checkout.html", rows=cart_rows(), subtotal=cart_subtotal())
        try:
            # Re-check current prices and stock on the server, inside the order transaction.
            rows = cart_rows()
            subtotal = sum(r["product"].price * r["quantity"] for r in rows)
            if not rows:
                raise ValueError("Your cart is no longer available.")
            for row in rows:
                p = db.session.get(Product, row["product"].id)
                if not p or not p.is_active or p.stock < row["quantity"]:
                    raise ValueError(f"Stock changed for {row['product'].name}. Please update your cart.")
            order = Order(
                order_number="NBS-" + secrets.token_hex(4).upper(),
                user_id=current_user.id, full_name=full_name, phone=phone,
                address=address, city=city, state=state, pincode=pincode,
                subtotal=subtotal, shipping=0, total=subtotal,
                payment_method="COD", payment_status="Pending", status="Placed"
            )
            db.session.add(order)
            db.session.flush()
            for row in rows:
                p = db.session.get(Product, row["product"].id)
                p.stock -= row["quantity"]
                db.session.add(OrderItem(order_id=order.id, product_id=p.id, product_name=p.name,
                                         unit_price=p.price, quantity=row["quantity"]))
            db.session.commit()
            session["cart"] = {}
            flash("Order placed successfully. Payment is Cash on Delivery.", "success")
            return redirect(url_for("order_detail", order_id=order.id))
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "error")
    return render_template("checkout.html", rows=cart_rows(), subtotal=cart_subtotal())

def cart_rows():
    result = []
    for pid, qty in session.get("cart", {}).items():
        if str(pid).isdigit() and str(qty).isdigit():
            p = Product.query.filter_by(id=int(pid), is_active=True).first()
            q = int(qty)
            if p and q > 0:
                result.append({"product": p, "quantity": q})
    return result

def cart_subtotal():
    return sum(r["product"].price * r["quantity"] for r in cart_rows())

@app.route("/dashboard")
@login_required
def dashboard():
    recent_orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).limit(5).all()
    return render_template("dashboard.html", orders=recent_orders)

@app.route("/orders")
@login_required
def my_orders():
    orders = Order.query.filter_by(user_id=current_user.id).order_by(Order.created_at.desc()).all()
    return render_template("orders.html", orders=orders, admin_view=False)

@app.route("/orders/<int:order_id>")
@login_required
def order_detail(order_id):
    order = Order.query.filter_by(id=order_id).first_or_404()
    if order.user_id != current_user.id and not current_user.is_admin:
        abort(403)
    return render_template("order_detail.html", order=order)

@app.route("/admin")
@admin_required
def admin_dashboard():
    from sqlalchemy import func
    sales = db.session.query(func.coalesce(func.sum(Order.total), 0)).filter(Order.status != "Cancelled").scalar()
    total_orders = Order.query.count()
    customers = User.query.filter_by(is_admin=False).count()
    products_count = Product.query.count()
    pending = Order.query.filter_by(status="Placed").count()
    low_stock = Product.query.filter(Product.stock <= 5, Product.is_active.is_(True)).count()
    recent_orders = Order.query.order_by(Order.created_at.desc()).limit(8).all()
    best_sellers = db.session.query(OrderItem.product_name, func.sum(OrderItem.quantity).label("qty")).group_by(OrderItem.product_name).order_by(func.sum(OrderItem.quantity).desc()).limit(5).all()
    return render_template("admin_dashboard.html", sales=sales, total_orders=total_orders, customers=customers,
                           products_count=products_count, pending=pending, low_stock=low_stock,
                           recent_orders=recent_orders, best_sellers=best_sellers)

@app.route("/admin/products")
@admin_required
def admin_products():
    q = request.args.get("q", "").strip()
    products = Product.query.filter(Product.name.ilike(f"%{q}%")).order_by(Product.created_at.desc()).all() if q else Product.query.order_by(Product.created_at.desc()).all()
    return render_template("admin_products.html", products=products)

@app.route("/admin/products/new", methods=["GET", "POST"])
@app.route("/admin/products/<int:product_id>/edit", methods=["GET", "POST"])
@admin_required
def admin_product_form(product_id=None):
    product = db.session.get(Product, product_id) if product_id else Product()
    if product_id and not product:
        abort(404)
    if request.method == "POST":
        try:
            name = request.form.get("name", "").strip()[:160]
            if len(name) < 2:
                raise ValueError("Product name is required.")
            price = parse_int(request.form.get("price"), 1, 100000000)
            stock = parse_int(request.form.get("stock"), 0, 10000000)
            compare_raw = request.form.get("compare_price", "").strip()
            compare_price = parse_int(compare_raw, 1, 100000000) if compare_raw else None
            sku = request.form.get("sku", "").strip()[:80] or None
            if sku and Product.query.filter(Product.sku == sku, Product.id != (product.id or 0)).first():
                raise ValueError("SKU already exists.")
            product.name = name
            product.description = request.form.get("description", "").strip()[:10000]
            product.price = price
            product.compare_price = compare_price
            product.stock = stock
            product.sku = sku
            product.is_featured = bool(request.form.get("is_featured"))
            product.is_active = bool(request.form.get("is_active"))
            category_id = request.form.get("category_id", "")
            product.category_id = int(category_id) if category_id.isdigit() else None
            upload = request.files.get("image")
            if upload and upload.filename:
                if not allowed_file(upload.filename):
                    raise ValueError("Image must be PNG, JPG, JPEG, WEBP, or GIF.")
                filename = secure_filename(upload.filename)
                unique_name = secrets.token_hex(8) + "_" + filename
                upload_dir = os.path.join(BASE_DIR, "static", "uploads")
                os.makedirs(upload_dir, exist_ok=True)
                upload.save(os.path.join(upload_dir, unique_name))
                product.image_url = url_for("static", filename="uploads/" + unique_name)
            if not product.id:
                db.session.add(product)
            db.session.commit()
            flash("Product saved.", "success")
            return redirect(url_for("admin_products"))
        except ValueError as e:
            db.session.rollback()
            flash(str(e), "error")
    return render_template("admin_product_form.html", product=product, categories=Category.query.order_by(Category.name).all())

@app.route("/admin/products/<int:product_id>/delete", methods=["POST"])
@admin_required
def admin_product_delete(product_id):
    product = db.session.get(Product, product_id) or abort(404)
    # Keep old order item snapshots and avoid deleting linked product rows.
    product.is_active = False
    db.session.commit()
    flash("Product deactivated (order history preserved).", "success")
    return redirect(url_for("admin_products"))

@app.route("/admin/orders")
@admin_required
def admin_orders():
    orders = Order.query.order_by(Order.created_at.desc()).all()
    return render_template("orders.html", orders=orders, admin_view=True)

@app.route("/admin/orders/<int:order_id>/status", methods=["POST"])
@admin_required
def admin_order_status(order_id):
    order = db.session.get(Order, order_id) or abort(404)
    status = request.form.get("status", "")
    if status not in {"Placed", "Processing", "Shipped", "Delivered", "Cancelled"}:
        flash("Invalid order status.", "error")
    elif order.status == "Cancelled" and status != "Cancelled":
        flash("Cancelled orders cannot be reopened in this starter.", "error")
    else:
        if status == "Cancelled" and order.status != "Cancelled":
            for item in order.items:
                if item.product_id:
                    p = db.session.get(Product, item.product_id)
                    if p:
                        p.stock += item.quantity
        order.status = status
        db.session.commit()
        flash("Order status updated.", "success")
    return redirect(url_for("admin_orders"))

@app.route("/admin/customers")
@admin_required
def admin_customers():
    customers = User.query.filter_by(is_admin=False).order_by(User.created_at.desc()).all()
    return render_template("admin_customers.html", customers=customers)

@app.route("/admin/categories", methods=["GET", "POST"])
@admin_required
def admin_categories():
    if request.method == "POST":
        name = request.form.get("name", "").strip()[:80]
        slug = "-".join(name.lower().split())[:100]
        if not name:
            flash("Category name is required.", "error")
        elif Category.query.filter((Category.name == name) | (Category.slug == slug)).first():
            flash("Category already exists.", "error")
        else:
            db.session.add(Category(name=name, slug=slug))
            db.session.commit()
            flash("Category created.", "success")
            return redirect(url_for("admin_categories"))
    return render_template("admin_categories.html", categories=Category.query.order_by(Category.name).all())

@app.route("/about")
def about():
    return render_template("info.html", page_title="About Us", body="Nanu Bhai Store — Shop Smart, Live Better. We are building a simple, reliable shopping experience.")

@app.route("/contact")
def contact():
    return render_template("info.html", page_title="Contact Us", body="For support, replace this text with your verified business email and contact number before publishing.")

@app.errorhandler(403)
def forbidden(error):
    return render_template("error.html", code=403, message="You do not have permission to view this page."), 403

@app.errorhandler(404)
def not_found(error):
    return render_template("error.html", code=404, message="The page or product could not be found."), 404

@app.cli.command("unused-placeholder")
def unused_placeholder():
    pass

def seed_demo_data():
    if Category.query.count() == 0:
        categories = [
            Category(name="Electronics", slug="electronics"),
            Category(name="Fashion", slug="fashion"),
            Category(name="Accessories", slug="accessories"),
            Category(name="Home & Living", slug="home-living"),
        ]
        db.session.add_all(categories)
        db.session.flush()
    if Product.query.count() == 0:
        cats = {c.slug: c.id for c in Category.query.all()}
        demos = [
            ("Wireless Headphones", "Comfortable wireless headphones with rich sound and everyday battery life.", 1999, 2499, 25, "NBS-HEAD-01", "https://images.unsplash.com/photo-1505740420928-5e560c06d30e?w=700", "electronics", True),
            ("Smart Watch", "A smart everyday watch with fitness features and a clean display.", 2999, 3499, 18, "NBS-WATCH-01", "https://images.unsplash.com/photo-1523275335684-37898b6baf30?w=700", "electronics", True),
            ("Running Shoes", "Lightweight running shoes designed for daily training and walks.", 2499, 2999, 30, "NBS-SHOE-01", "https://images.unsplash.com/photo-1542291026-7eec264c27ff?w=700", "fashion", True),
            ("Everyday Backpack", "A practical backpack for college, work and travel.", 1499, 1799, 20, "NBS-BAG-01", "https://images.unsplash.com/photo-1553062407-98eeb64c6a62?w=700", "accessories", True),
            ("Classic T-Shirt", "Soft cotton everyday T-shirt. Simple, comfortable and versatile.", 799, 999, 40, "NBS-TSHIRT-01", "https://images.unsplash.com/photo-1521572163474-6864f9cf17ab?w=700", "fashion", False),
            ("Desk Lamp", "Minimal desk lamp for study tables and home offices.", 1199, 1499, 12, "NBS-LAMP-01", "https://images.unsplash.com/photo-1507473885765-e6ed057f782c?w=700", "home-living", False),
        ]
        for name, desc, price, compare, stock, sku, image, cat, featured in demos:
            db.session.add(Product(name=name, description=desc, price=price, compare_price=compare, stock=stock,
                                   sku=sku, image_url=image, category_id=cats.get(cat), is_featured=featured, is_active=True))
    db.session.commit()

@app.cli.command("init-db")
def init_db_cli():
    """Create missing tables and insert sample products; existing data is not deleted."""
    db.create_all()
    seed_demo_data()
    click.echo("Database ready. Existing records were preserved.")

@app.cli.command("create-admin")
def create_admin_cli():
    """Create an admin account interactively."""
    email = click.prompt("Admin email").strip().lower()
    name = click.prompt("Admin display name", default="Store Admin").strip()
    password = click.prompt("Admin password", hide_input=True, confirmation_prompt=True)
    if len(password) < 12:
        raise click.ClickException("Use at least 12 characters for an admin password.")
    if User.query.filter_by(email=email).first():
        raise click.ClickException("That email already exists. Do not promote an account automatically; use a reviewed admin setup process.")
    user = User(name=name, email=email, is_admin=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()
    click.echo("Admin created successfully.")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] in {"init-db", "create-admin"}:
        with app.app_context():
            db.create_all()
            if sys.argv[1] == "init-db":
                seed_demo_data()
                print("Database ready; existing records preserved.")
            else:
                email = input("Admin email: ").strip().lower()
                name = input("Admin display name [Store Admin]: ").strip() or "Store Admin"
                import getpass
                password = getpass.getpass("Admin password (12+ chars): ")
                confirm = getpass.getpass("Confirm password: ")
                if len(password) < 12 or password != confirm:
                    raise SystemExit("Password must be 12+ chars and match confirmation.")
                if User.query.filter_by(email=email).first():
                    raise SystemExit("Email already exists; no changes made.")
                admin = User(name=name, email=email, is_admin=True)
                admin.set_password(password)
                db.session.add(admin)
                db.session.commit()
                print("Admin created.")
    else:
        app.run(host="127.0.0.1", port=5000, debug=True)
