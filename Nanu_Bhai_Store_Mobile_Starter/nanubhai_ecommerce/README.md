# Nanu Bhai Store — Mobile Starter

A Flask + SQLite starter for Termux and Acode. Includes customer registration/login, product catalogue, session cart, checkout/order records, customer order history, and a protected admin area for product/order management.

## Run in Termux

```bash
pkg update && pkg upgrade -y
pkg install python -y
python -m pip install --upgrade pip
cd ~/nanubhai_ecommerce
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python app.py init-db
python app.py create-admin
python app.py run
```

Open `http://127.0.0.1:5000` in your phone browser. Keep Termux open while using the development server.

## Admin setup

`python app.py create-admin` prompts for an email and password. Do not use a weak password. Admin access is assigned only by this command, not by public registration.

## Acode access

Recommended: keep project in Termux home (`~/nanubhai_ecommerce`) for Python package and permission reliability. If your Acode build cannot edit Termux home, use Termux's shared storage route:

```bash
termux-setup-storage
mkdir -p ~/storage/shared/nanubhai_ecommerce
```

Acode can edit files in `Internal storage/nanubhai_ecommerce`, but running Python directly from shared storage can have permission/path issues. If you choose shared storage, copy the project into Termux home before running.

## Important scope notes

This is a functional local MVP, not a finished production commerce platform. It includes server-side price and stock checks, password hashing, CSRF protection for POST forms, login-required order pages, and admin checks. It does **not** claim to include configured Google OAuth, email verification/reset, online payment provider, shipping API, tax rules, review moderation, digital downloads, or production deployment. Those require separate configuration and testing. Checkout currently creates a Cash on Delivery order only.

Before public deployment: set a strong `SECRET_KEY`, use HTTPS and a production WSGI server, configure backups/migrations, add rate limiting and email/payment integrations, and run the test suite.
