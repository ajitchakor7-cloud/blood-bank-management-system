# app.py - Blood Bank Management System (Flask + MongoDB)

from datetime import datetime
from functools import wraps

from bson import ObjectId
from bson.errors import InvalidId
from flask import (Flask, render_template, request, redirect,
                   url_for, session, flash)
from werkzeug.security import check_password_hash

from database import (admins, donors, blood_stock, hospitals,
                      blood_requests, BLOOD_GROUPS, init_db)

app = Flask(__name__)
app.secret_key = "change-this-secret-key"   # needed for session & flash

init_db()   # create default admin + stock records on start


# ---------------- HELPERS ----------------
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "admin" not in session:
            flash("Please login first.", "error")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper


def to_id(value):
    """Convert string to ObjectId safely (returns None if invalid)."""
    try:
        return ObjectId(value)
    except (InvalidId, TypeError):
        return None


def to_int(value, default=None):
    try:
        return int(value)
    except (ValueError, TypeError):
        return default


# ---------------- AUTH ----------------
@app.route("/")
def home():
    return redirect(url_for("dashboard") if "admin" in session else url_for("login"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        admin = admins.find_one({"username": username})
        if admin and check_password_hash(admin["password"], password):
            session["admin"] = username
            flash("Login successful. Welcome, " + username + "!", "success")
            return redirect(url_for("dashboard"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login"))


# ---------------- DASHBOARD ----------------
@app.route("/dashboard")
@login_required
def dashboard():
    stats = {
        "donors": donors.count_documents({}),
        "hospitals": hospitals.count_documents({}),
        "total_units": sum(s["units"] for s in blood_stock.find()),
        "pending": blood_requests.count_documents({"status": "Pending"}),
        "approved": blood_requests.count_documents({"status": "Approved"}),
        "issued": blood_requests.count_documents({"status": "Issued"}),
        "rejected": blood_requests.count_documents({"status": "Rejected"}),
    }
    stock = list(blood_stock.find().sort("blood_group", 1))
    recent = list(blood_requests.find().sort("request_date", -1).limit(5))
    return render_template("dashboard.html", stats=stats, stock=stock, recent=recent)


# ---------------- DONORS ----------------
@app.route("/donors")
@login_required
def donor_list():
    q = request.args.get("q", "").strip()
    query = {}
    if q:
        query = {"$or": [
            {"name": {"$regex": q, "$options": "i"}},
            {"blood_group": {"$regex": "^" + q.replace("+", r"\+") + "$", "$options": "i"}},
            {"phone": {"$regex": q}},
            {"address": {"$regex": q, "$options": "i"}},
        ]}
    data = list(donors.find(query).sort("created_at", -1))
    return render_template("donors.html", donors=data, q=q)


def read_donor_form():
    f = request.form
    donor = {
        "name": f.get("name", "").strip(),
        "age": to_int(f.get("age")),
        "gender": f.get("gender", ""),
        "blood_group": f.get("blood_group", ""),
        "phone": f.get("phone", "").strip(),
        "email": f.get("email", "").strip(),
        "address": f.get("address", "").strip(),
        "last_donation_date": f.get("last_donation_date", ""),
    }
    error = None
    if not donor["name"]:
        error = "Name is required."
    elif donor["age"] is None or not (18 <= donor["age"] <= 65):
        error = "Donor age must be between 18 and 65."
    elif donor["blood_group"] not in BLOOD_GROUPS:
        error = "Select a valid blood group."
    elif not (donor["phone"].isdigit() and len(donor["phone"]) == 10):
        error = "Phone must be exactly 10 digits."
    return donor, error


@app.route("/donors/add", methods=["GET", "POST"])
@login_required
def donor_add():
    if request.method == "POST":
        donor, error = read_donor_form()
        if error:
            flash(error, "error")
            return render_template("donor_form.html", donor=donor, groups=BLOOD_GROUPS, mode="Add")
        donor["created_at"] = datetime.now()
        donors.insert_one(donor)
        flash("Donor added successfully.", "success")
        return redirect(url_for("donor_list"))
    return render_template("donor_form.html", donor={}, groups=BLOOD_GROUPS, mode="Add")


@app.route("/donors/edit/<id>", methods=["GET", "POST"])
@login_required
def donor_edit(id):
    oid = to_id(id)
    donor = donors.find_one({"_id": oid}) if oid else None
    if not donor:
        flash("Donor not found.", "error")
        return redirect(url_for("donor_list"))
    if request.method == "POST":
        new, error = read_donor_form()
        if error:
            flash(error, "error")
            new["_id"] = oid
            return render_template("donor_form.html", donor=new, groups=BLOOD_GROUPS, mode="Edit")
        donors.update_one({"_id": oid}, {"$set": new})
        flash("Donor updated successfully.", "success")
        return redirect(url_for("donor_list"))
    return render_template("donor_form.html", donor=donor, groups=BLOOD_GROUPS, mode="Edit")


@app.route("/donors/delete/<id>", methods=["POST"])
@login_required
def donor_delete(id):
    oid = to_id(id)
    if oid:
        donors.delete_one({"_id": oid})
        flash("Donor deleted.", "success")
    return redirect(url_for("donor_list"))


# ---------------- BLOOD STOCK ----------------
@app.route("/stock")
@login_required
def stock_view():
    stock = list(blood_stock.find().sort("blood_group", 1))
    return render_template("stock.html", stock=stock, groups=BLOOD_GROUPS)


@app.route("/stock/add", methods=["POST"])
@login_required
def stock_add():
    group = request.form.get("blood_group")
    units = to_int(request.form.get("units"))
    if group not in BLOOD_GROUPS or units is None or units <= 0:
        flash("Select a blood group and enter units greater than 0.", "error")
    else:
        # AUTOMATIC INCREASE
        blood_stock.update_one({"blood_group": group},
                               {"$inc": {"units": units},
                                "$set": {"last_updated": datetime.now()}})
        flash(f"{units} unit(s) of {group} added to stock.", "success")
    return redirect(url_for("stock_view"))


@app.route("/stock/update", methods=["POST"])
@login_required
def stock_update():
    group = request.form.get("blood_group")
    units = to_int(request.form.get("units"))
    if group not in BLOOD_GROUPS or units is None or units < 0:
        flash("Enter a valid number of units (0 or more).", "error")
    else:
        blood_stock.update_one({"blood_group": group},
                               {"$set": {"units": units, "last_updated": datetime.now()}})
        flash(f"Stock of {group} updated to {units} unit(s).", "success")
    return redirect(url_for("stock_view"))


# ---------------- HOSPITALS ----------------
def read_hospital_form():
    f = request.form
    h = {
        "name": f.get("name", "").strip(),
        "city": f.get("city", "").strip(),
        "phone": f.get("phone", "").strip(),
        "email": f.get("email", "").strip(),
        "address": f.get("address", "").strip(),
    }
    error = None
    if not h["name"] or not h["city"]:
        error = "Hospital name and city are required."
    elif not (h["phone"].isdigit() and len(h["phone"]) == 10):
        error = "Phone must be exactly 10 digits."
    return h, error


@app.route("/hospitals")
@login_required
def hospital_list():
    data = list(hospitals.find().sort("name", 1))
    return render_template("hospitals.html", hospitals=data)


@app.route("/hospitals/add", methods=["GET", "POST"])
@login_required
def hospital_add():
    if request.method == "POST":
        h, error = read_hospital_form()
        if error:
            flash(error, "error")
            return render_template("hospital_form.html", hospital=h, mode="Add")
        h["created_at"] = datetime.now()
        hospitals.insert_one(h)
        flash("Hospital added successfully.", "success")
        return redirect(url_for("hospital_list"))
    return render_template("hospital_form.html", hospital={}, mode="Add")


@app.route("/hospitals/edit/<id>", methods=["GET", "POST"])
@login_required
def hospital_edit(id):
    oid = to_id(id)
    h = hospitals.find_one({"_id": oid}) if oid else None
    if not h:
        flash("Hospital not found.", "error")
        return redirect(url_for("hospital_list"))
    if request.method == "POST":
        new, error = read_hospital_form()
        if error:
            flash(error, "error")
            new["_id"] = oid
            return render_template("hospital_form.html", hospital=new, mode="Edit")
        hospitals.update_one({"_id": oid}, {"$set": new})
        flash("Hospital updated successfully.", "success")
        return redirect(url_for("hospital_list"))
    return render_template("hospital_form.html", hospital=h, mode="Edit")


@app.route("/hospitals/delete/<id>", methods=["POST"])
@login_required
def hospital_delete(id):
    oid = to_id(id)
    if oid:
        hospitals.delete_one({"_id": oid})
        flash("Hospital deleted.", "success")
    return redirect(url_for("hospital_list"))


# ---------------- BLOOD REQUESTS ----------------
@app.route("/requests")
@login_required
def request_list():
    status = request.args.get("status", "")
    query = {"status": status} if status else {}
    data = list(blood_requests.find(query).sort("request_date", -1))
    return render_template("requests.html", requests=data, status=status)


@app.route("/requests/add", methods=["GET", "POST"])
@login_required
def request_add():
    hosp = list(hospitals.find().sort("name", 1))
    if request.method == "POST":
        f = request.form
        hid = to_id(f.get("hospital_id"))
        hospital = hospitals.find_one({"_id": hid}) if hid else None
        group = f.get("blood_group")
        units = to_int(f.get("units"))
        patient = f.get("patient_name", "").strip()
        if not hospital:
            flash("Please select a hospital (add one first if the list is empty).", "error")
        elif not patient:
            flash("Patient name is required.", "error")
        elif group not in BLOOD_GROUPS or units is None or units <= 0:
            flash("Select a blood group and units greater than 0.", "error")
        else:
            blood_requests.insert_one({
                "hospital_id": hospital["_id"],
                "hospital_name": hospital["name"],
                "patient_name": patient,
                "blood_group": group,
                "units": units,
                "status": "Pending",
                "request_date": datetime.now(),
            })
            flash("Blood request added (status: Pending).", "success")
            return redirect(url_for("request_list"))
    return render_template("request_form.html", hospitals=hosp, groups=BLOOD_GROUPS)


@app.route("/requests/<id>/<action>", methods=["POST"])
@login_required
def request_action(id, action):
    oid = to_id(id)
    req = blood_requests.find_one({"_id": oid}) if oid else None
    if not req:
        flash("Request not found.", "error")
        return redirect(url_for("request_list"))

    status = req["status"]

    if action == "approve" and status == "Pending":
        blood_requests.update_one({"_id": oid}, {"$set": {"status": "Approved"}})
        flash("Request approved.", "success")

    elif action == "reject" and status in ("Pending", "Approved"):
        blood_requests.update_one({"_id": oid}, {"$set": {"status": "Rejected"}})
        flash("Request rejected.", "success")

    elif action == "issue" and status == "Approved":
        stock = blood_stock.find_one({"blood_group": req["blood_group"]})
        if stock["units"] < req["units"]:
            flash(f"Not enough {req['blood_group']} stock. Available: {stock['units']} unit(s).", "error")
        else:
            # AUTOMATIC DECREASE
            blood_stock.update_one({"blood_group": req["blood_group"]},
                                   {"$inc": {"units": -req["units"]},
                                    "$set": {"last_updated": datetime.now()}})
            blood_requests.update_one({"_id": oid}, {"$set": {"status": "Issued"}})
            flash(f"{req['units']} unit(s) of {req['blood_group']} issued. Stock decreased.", "success")
    else:
        flash("This action is not allowed for the current status.", "error")

    return redirect(url_for("request_list"))


# ---------------- BLOOD AVAILABILITY SEARCH ----------------
@app.route("/search")
@login_required
def search():
    group = request.args.get("blood_group", "")
    stock = None
    matching_donors = []
    if group in BLOOD_GROUPS:
        stock = blood_stock.find_one({"blood_group": group})
        matching_donors = list(donors.find({"blood_group": group}).sort("name", 1))
    return render_template("search.html", groups=BLOOD_GROUPS, group=group,
                           stock=stock, donors=matching_donors)


if __name__ == "__main__":
    app.run(debug=True)
