from flask import Flask, request, session, redirect, render_template, render_template_string, send_from_directory
import json, os, random, datetime
from urllib.parse import quote_plus

app = Flask(__name__)
# secret key should come from environment in production
app.secret_key = os.getenv("SECRET_KEY", "tajnyklucz123")
DB_FILE = "users.json"
RATE_FILE = "tbuy_rate.json"

# bazowy kurs: 1 TCOIN = 5.50 zł
BASE_TBUY_RATE = 5.50

# ---------- POMOCNICZE ----------

def load_users():
    if not os.path.exists(DB_FILE):
        return {}
    with open(DB_FILE, "r") as f:
        try:
            return json.load(f)
        except json.JSONDecodeError:
            return {}

def save_users(users):
    with open(DB_FILE, "w") as f:
        json.dump(users, f, indent=4)

def get_next_id(users):
    return str(max(map(int, users.keys())) + 1) if users else "2"

def find_user(users, username):
    for uid, u in users.items():
        if u["username"] == username:
            return uid
    return None

def load_tbuy_rate():
    """
    Zwraca dzisiejszy kurs TCOIN.
    Co dzień może się zmienić o losową wartość z zakresu 1–100 zł (w górę lub w dół).
    """
    today = datetime.date.today().isoformat()

    # jeśli plik z kursem nie istnieje → startujemy od bazowego kursu
    if not os.path.exists(RATE_FILE):
        rate = BASE_TBUY_RATE
        data = {"date": today, "rate": rate}
        with open(RATE_FILE, "w") as f:
            json.dump(data, f)
        return rate

    # wczytaj zapisany kurs
    try:
        with open(RATE_FILE, "r") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        # jak coś się popsuje z plikiem, wracamy do bazowego
        rate = BASE_TBUY_RATE
        data = {"date": today, "rate": rate}
        with open(RATE_FILE, "w") as f:
            json.dump(data, f)
        return rate

    saved_date = data.get("date")
    rate = float(data.get("rate", BASE_TBUY_RATE))

    # jeśli to już dzisiejszy kurs → zwróć go
    if saved_date == today:
        return rate

    # nowy dzień → kurs zmienia się losowo o 1–100 zł w górę lub w dół
    change_zl = random.randint(1, 100)
    direction = random.choice([-1, 1])
    rate += direction * change_zl

    # nie pozwalamy spaść kursowi poniżej bazowego kursu 5.50 zł
    if rate < BASE_TBUY_RATE:
        rate = BASE_TBUY_RATE

    data = {"date": today, "rate": rate}
    with open(RATE_FILE, "w") as f:
        json.dump(data, f)

    return rate

def get_current_uid():
    """
    Zwraca ID użytkownika na podstawie tokenu karty (tab),
    a jeśli go nie ma – z pola session["user_id"].
    """
    tab = request.args.get("tab") or request.form.get("tab")
    tabs = session.get("tabs", {})
    if tab and tab in tabs:
        return tabs[tab], tab
    # Fallback – stary mechanizm, jedna sesja na przeglądarkę
    uid = session.get("user_id")
    return uid, None

def create_tab_for_uid(uid):
    """
    Tworzy nowy token karty (tab) powiązany z danym użytkownikiem.
    """
    tabs = session.get("tabs", {})
    # Prosty losowy token wystarczający do odróżnienia kart
    while True:
        tab = str(random.randint(100000, 999999))
        if tab not in tabs:
            break
    tabs[tab] = uid
    session["tabs"] = tabs
    return tab

# ---------- LOGIN / REGISTER ----------

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        users = load_users()
        username = request.form["username"]
        password = request.form["password"]

        uid = find_user(users, username)
        if uid:
            if users[uid]["password"] == password:
                session["user_id"] = uid
                # tworzymy osobny "token karty" tak, aby można było mieć kilka kont w 1 przeglądarce
                tab = create_tab_for_uid(uid)
                return redirect(f"/menu?tab={tab}")
            else:
                return render_template(
                    "login.html",
                    error="Złe hasło",
                    username=username,
                    offer_register=False,
                    reg_username="",
                    reg_password="",
                )
        else:
            return render_template(
                "login.html",
                error="",
                username=username,
                offer_register=True,
                reg_username=username,
                reg_password=password,
            )
    return render_template(
        "login.html",
        error="",
        username="",
        offer_register=False,
        reg_username="",
        reg_password="",
    )

@app.route("/register", methods=["POST"])
def register():
    users = load_users()
    new_id = get_next_id(users)

    users[new_id] = {
        "username": request.form["username"],
        "password": request.form["password"],
        "balance": 0,
        "role": "user"
    }
    save_users(users)
    session["user_id"] = new_id
    tab = create_tab_for_uid(new_id)
    return redirect(f"/menu?tab={tab}")

# ---------- MENU UŻYTKOWNIKA ----------

@app.route("/menu", methods=["GET", "POST"])
def menu():
    uid, tab = get_current_uid()
    if not uid:
        return redirect("/")

    users = load_users()
    user = users[uid]


    # ADMIN PANEL
    if user.get("role") == "admin":
        # dane do wyświetlenia w panelu admina
        current_rate = load_tbuy_rate()

        # przekazujemy tab dalej, aby odróżnić karty
        return render_template("admin_panel.html", current_rate=current_rate, tab=tab or "")

    # NORMALNY USER
    # token przypisujemy do konkretnej karty (tab), żeby się nie mieszał między zakładkami
    tokens = session.get("tokens", {})
    if tab and tab in tokens:
        token_value = tokens[tab]
    else:
        # fallback do starego mechanizmu, jeśli coś jeszcze używa session["current_token"]
        token_value = session.get("current_token", "")
    # allow passing an error message from redirects (e.g. invalid amount)
    message = request.args.get("error", "")

    # POST – zatwierdzenie transakcji
    if request.method == "POST":
        user_auth = (request.form.get("auth") or "").strip()
        if token_value:
            raw = token_value.replace("TPAY:", "")
            user_id, action, amount, token_auth = raw.split("Z")
            token_auth = str(token_auth)
            # amount w tokenie = ilość TCOIN, kropka zapisana jako 'X'
            amount_str = (
                str(amount)
                .strip()
                .replace("X", ".")
                .replace(",", ".")
            )
            try:
                amount = float(amount_str)
            except ValueError:
                message = "Błędna wartość kwoty w tokenie."
            else:
                if not user_auth:
                    message = "Musisz podać AUTH od admina."
                elif not user_auth.isdigit():
                    message = "AUTH musi składać się tylko z cyfr."
                elif user_auth != token_auth:
                    message = "Zły AUTH!"
                else:
                    # aktualny kurs TCOIN na dziś
                    current_rate = load_tbuy_rate()
                    # kwota w PLN po przeliczeniu z TCOIN
                    value_pln = amount * current_rate
                    if action == "0":  # Kupno TCOIN (zasilenie salda w zł)
                        users[uid]["balance"] += value_pln
                        message = (
                            f"Transakcja kupna zatwierdzona! "
                            f"Kupiłeś {amount} TCOIN (wartość {value_pln} zł). "
                            f"Twoje nowe saldo: {users[uid]['balance']} zł."
                        )
                    else:  # Sprzedaż TCOIN (zmniejszenie salda w zł)
                        if users[uid]["balance"] < value_pln:
                            message = (
                                f"Nie masz wystarczającego salda! "
                                f"Potrzeba {value_pln} zł, a masz: {users[uid]['balance']} zł."
                            )
                        else:
                            users[uid]["balance"] -= value_pln
                            message = (
                                f"Transakcja sprzedaży zatwierdzona! "
                                f"Sprzedałeś {amount} TCOIN (wartość {value_pln} zł). "
                                f"Twoje nowe saldo: {users[uid]['balance']} zł."
                            )
                    save_users(users)
                    # usuwamy token tylko dla tej konkretnej karty
                    if tab and tab in tokens:
                        tokens.pop(tab, None)
                        session["tokens"] = tokens
                    # oraz stary globalny token (na wszelki wypadek)
                    session.pop("current_token", None)
                    token_value = ""
        else:
            message = "Nie masz wygenerowanego tokena!"

    current_rate = load_tbuy_rate()
    balance_pln = float(user.get("balance", 0) or 0)
    balance_tcoin = balance_pln / current_rate if current_rate else 0

    return render_template(
        "menu.html",
        tcoin_rate=current_rate,
        balance_pln=balance_pln,
        balance_tcoin=balance_tcoin,
        token_value=token_value,
        message=message,
        tab=tab or "",
    )

# ---------- GENEROWANIE TOKENA – ZAPIS W SESJI ----------

@app.route("/generate_token", methods=["POST"])
def generate_token_menu():
    uid, tab = get_current_uid()
    if not uid:
        return redirect("/")
    users = load_users()
    user = users[uid]

    action = request.form["action"]
    # keep the original input to build token (convert '.' and ',' to 'X')
    amount_input = (request.form.get("amount") or "").strip()
    amount_token = amount_input.replace(" ", "").replace(".", "X").replace(",", "X")
    try:
        amount = float(amount_input.replace(",", "."))
    except ValueError:
        err = "Błędna wartość ilości (użyj liczb, np. 10 lub 10.5)."
        if tab:
            return redirect(f"/menu?tab={tab}&error={quote_plus(err)}")
        return redirect(f"/menu?error={quote_plus(err)}")

    # jeśli akcja = sprzedaż i saldo jest mniejsze niż ilość → blokada
    if action == "1" and user["balance"] < amount:
        if tab:
            return f"Nie masz wystarczającego salda, aby wygenerować token do sprzedaży! Twoje saldo: {user['balance']}<br><a href='/menu?tab={tab}'>Powrót</a>"
        return f"Nie masz wystarczającego salda, aby wygenerować token do sprzedaży! Twoje saldo: {user['balance']}<br><a href='/menu'>Powrót</a>"

    token_auth = str(random.randint(1000, 9999))
    token = f"TPAY:{uid}Z{action}Z{amount_token}Z{token_auth}"

    # zapisujemy token osobno dla każdej karty (tab),
    # żeby inne zakładki go nie widziały
    if tab:
        tokens = session.get("tokens", {})
        tokens[tab] = token
        session["tokens"] = tokens
    else:
        # fallback do starego pola globalnego
        session["current_token"] = token

    # wracamy do tego samego "widoku karty"
    if tab:
        return redirect(f"/menu?tab={tab}")
    return redirect("/menu")

# ---------- ADMIN: DESZYFROWANIE TOKENÓW ----------

@app.route("/admin/decode_token", methods=["GET", "POST"])
def admin_decode_token():
    uid, tab = get_current_uid()
    if not uid:
        return redirect("/")
    users = load_users()
    if users[uid].get("role") != "admin":
        return "Brak uprawnień", 403
    if request.method == "POST":
        token = request.form.get("token", "")
        if not token.startswith("TPAY:"):
            return render_template("admin_decode.html", tab=tab or "", error="To nie token TPAY", show_result=False)
        raw = token.replace("TPAY:", "")
        try:
            user_id, action, amount, token_auth = raw.split("Z")
        except ValueError:
            return render_template("admin_decode.html", tab=tab or "", error="Nieprawidłowy format tokena", show_result=False)

        username = users.get(user_id, {}).get("username", f"nieznany użytkownik (ID: {user_id})")

        # przeliczamy ilość TCOIN na zł
        current_rate = load_tbuy_rate()
        amount_str = (
            str(amount)
            .strip()
            .replace("X", ".")
            .replace(",", ".")
        )
        try:
            amount_tbuy = float(amount_str)
            value_pln = amount_tbuy * current_rate
            amount_text = f"{amount_tbuy} TCOIN (wartość {value_pln:.2f} zł przy kursie {current_rate:.2f} zł/TCOIN)"
        except ValueError:
            amount_text = f"(nie udało się przeliczyć) oryginalnie: {amount}"

        return render_template(
            "admin_decode.html",
            tab=tab or "",
            show_result=True,
            username=username,
            action_text=("KUPNO" if action == "0" else "SPRZEDAŻ"),
            amount_text=amount_text,
            auth=token_auth,
        )

    return render_template("admin_decode.html", tab=tab or "", show_result=False)


@app.route("/admin/force_rate", methods=["POST"])
def admin_force_rate():
    """
    Wymusza natychmiastową losową zmianę kursu TCOIN (1–100 zł w górę lub w dół),
    dostępne tylko dla admina. Po zmianie wraca do panelu admina.
    """
    uid, tab = get_current_uid()
    if not uid:
        return redirect("/")

    users = load_users()
    if users[uid].get("role") != "admin":
        return "Brak uprawnień", 403

    # pobieramy aktualny kurs (upewnia nas, że plik istnieje i ma dzisiejszą datę)
    current_rate = load_tbuy_rate()

    # losowa zmiana kursu 1–100 zł w górę lub w dół
    change_zl = random.randint(1, 100)
    direction = random.choice([-1, 1])
    new_rate = current_rate + direction * change_zl

    # nie pozwalamy spaść kursowi poniżej bazowego kursu
    if new_rate < BASE_TBUY_RATE:
        new_rate = BASE_TBUY_RATE

    today = datetime.date.today().isoformat()
    with open(RATE_FILE, "w") as f:
        json.dump({"date": today, "rate": new_rate}, f)

    # wracamy do panelu admina w tej samej karcie
    if tab:
        return redirect(f"/menu?tab={tab}")
    return redirect("/menu")


@app.route("/admin/reset_rate", methods=["POST"])
def admin_reset_rate():
    """
    Resetuje kurs TCOIN do wartości bazowej 5.50 zł (BASE_TBUY_RATE),
    dostępne tylko dla admina. Po zmianie wraca do panelu admina.
    """
    uid, tab = get_current_uid()
    if not uid:
        return redirect("/")

    users = load_users()
    if users[uid].get("role") != "admin":
        return "Brak uprawnień", 403

    today = datetime.date.today().isoformat()
    with open(RATE_FILE, "w") as f:
        json.dump({"date": today, "rate": BASE_TBUY_RATE}, f)

    if tab:
        return redirect(f"/menu?tab={tab}")
    return redirect("/menu")

# ---------- WYLOGUJ ----------

@app.route("/logout")
def logout():
    session.clear()
    return redirect("/")

# ---------- START ----------

if __name__ == "__main__":
    port = int(os.getenv("PORT", 5000))
    debug = os.getenv("FLASK_DEBUG", "False").lower() in ("1", "true", "yes")
    app.run(host="0.0.0.0", port=port, debug=debug)


@app.route('/icon.png')
def project_icon():
    # serve icon.png from project root
    return send_from_directory(app.root_path, 'icon.png')


@app.route('/favicon.ico')
def favicon():
    # Serve favicon from Flask static folder so browsers requesting /favicon.ico get the same image
    return app.send_static_file('icon.png')