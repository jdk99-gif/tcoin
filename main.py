from supabase import create_client, Client
from flask import Flask, request, session, redirect, render_template, render_template_string, send_from_directory
import os, random, datetime
from urllib.parse import quote_plus
from dotenv import load_dotenv

# Wczytaj zmienne środowiskowe z pliku .env
load_dotenv()

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "tajnyklucz123")

# Inicjalizacja Supabase
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("SUPABASE_URL i SUPABASE_KEY muszą być ustawione w zmiennych środowiskowych!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# bazowy kurs: 1 TCOIN = 5.50 zł
BASE_TBUY_RATE = 5.50

# ---------- POMOCNICZE ----------

def load_all_users():
    """Pobiera wszystkich użytkowników z Supabase"""
    try:
        response = supabase.table("users").select("*").execute()
        users = {}
        for user in response.data:
            users[str(user["id"])] = {
                "username": user["username"],
                "password": user["password"],
                "balance": user["balance"],
                "role": user["role"]
            }
        return users
    except Exception as e:
        print(f"Błąd przy wczytywaniu użytkowników: {e}")
        return {}

def get_user_by_id(uid):
    """Pobiera użytkownika po ID"""
    try:
        response = supabase.table("users").select("*").eq("id", int(uid)).execute()
        if response.data:
            user = response.data[0]
            return {
                "username": user["username"],
                "password": user["password"],
                "balance": user["balance"],
                "role": user["role"]
            }
        return None
    except Exception as e:
        print(f"Błąd przy wczytywaniu użytkownika: {e}")
        return None

def save_user_balance(uid, new_balance):
    """Aktualizuje saldo użytkownika"""
    try:
        supabase.table("users").update({"balance": new_balance}).eq("id", int(uid)).execute()
    except Exception as e:
        print(f"Błąd przy aktualizacji salda: {e}")

def get_next_id():
    """Pobiera kolejny dostępny ID użytkownika"""
    try:
        response = supabase.table("users").select("id").order("id", desc=True).limit(1).execute()
        if response.data:
            return str(response.data[0]["id"] + 1)
        return "2"  # ID admina = 1, pierwszego użytkownika = 2
    except Exception as e:
        print(f"Błąd przy pobieraniu następnego ID: {e}")
        return "2"

def find_user_by_username(username):
    """Znajduje użytkownika po nazwie"""
    try:
        response = supabase.table("users").select("id").eq("username", username).execute()
        if response.data:
            return str(response.data[0]["id"])
        return None
    except Exception as e:
        print(f"Błąd przy wyszukiwaniu użytkownika: {e}")
        return None

def load_tbuy_rate():
    """
    Zwraca dzisiejszy kurs TCOIN.
    Co dzień może się zmienić o losową wartość z zakresu 1–100 zł (w górę lub w dół).
    """
    today = datetime.date.today().isoformat()

    try:
        # Sprawdź czy istnieje kurs na dzisiaj
        response = supabase.table("exchange_rates").select("*").eq("date", today).execute()
        
        if response.data:
            # Kurs na dzisiaj już istnieje
            return float(response.data[0]["rate"])
        
        # Jeśli nie ma dzisiejszego kursu, pobierz ostatni
        response = supabase.table("exchange_rates").select("*").order("date", desc=True).limit(1).execute()
        
        if response.data:
            last_rate = float(response.data[0]["rate"])
        else:
            last_rate = BASE_TBUY_RATE
        
        # Nowy dzień → kurs zmienia się losowo o 1–100 zł w górę lub w dół
        change_zl = random.randint(1, 100)
        direction = random.choice([-1, 1])
        new_rate = last_rate + direction * change_zl
        
        # Nie pozwalamy spaść kursowi poniżej bazowego kursu
        if new_rate < BASE_TBUY_RATE:
            new_rate = BASE_TBUY_RATE
        
        # Zapisz nowy kurs
        supabase.table("exchange_rates").insert({
            "date": today,
            "rate": new_rate
        }).execute()
        
        return new_rate
    
    except Exception as e:
        print(f"Błąd przy wczytywaniu kursu: {e}")
        return BASE_TBUY_RATE

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

def encode_auth(auth_value: str) -> str:
    """Zapisuje AUTH od tyłu do tokena."""
    return str(auth_value)[::-1]

def decode_auth(encoded_auth: str) -> str:
    """Odkodowuje AUTH z tokena (odwrócenie ciągu)."""
    return str(encoded_auth)[::-1]

def set_menu_message(message, tab=None):
    """
    Zapisuje komunikat dla /menu bez przekazywania go w URL.
    Dla tab zapisujemy osobno, aby komunikaty nie mieszały się między kartami.
    """
    if tab:
        menu_messages = session.get("menu_messages", {})
        menu_messages[tab] = message
        session["menu_messages"] = menu_messages
    else:
        session["menu_message"] = message

def pop_menu_message(tab=None):
    """
    Pobiera i usuwa jednorazowy komunikat dla /menu.
    """
    if tab:
        menu_messages = session.get("menu_messages", {})
        message = menu_messages.pop(tab, "")
        session["menu_messages"] = menu_messages
        if message:
            return message
    return session.pop("menu_message", "")

# ---------- LOGIN / REGISTER ----------

@app.route("/", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]

        uid = find_user_by_username(username)
        if uid:
            user = get_user_by_id(uid)
            if user and user["password"] == password:
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
    username = request.form["username"]
    password = request.form["password"]
    
    # Sprawdź czy użytkownik już istnieje
    if find_user_by_username(username):
        return render_template(
            "login.html",
            error="Użytkownik już istnieje",
            username="",
            offer_register=False,
            reg_username="",
            reg_password="",
        )
    
    try:
        # Utwórz nowego użytkownika
        response = supabase.table("users").insert({
            "username": username,
            "password": password,
            "balance": 0,
            "role": "user"
        }).execute()
        
        new_id = str(response.data[0]["id"])
        session["user_id"] = new_id
        tab = create_tab_for_uid(new_id)
        return redirect(f"/menu?tab={tab}")
    except Exception as e:
        print(f"Błąd przy rejestracji: {e}")
        return render_template(
            "login.html",
            error="Błąd przy rejestracji",
            username="",
            offer_register=False,
            reg_username="",
            reg_password="",
        )

# ---------- MENU UŻYTKOWNIKA ----------

@app.route("/menu", methods=["GET", "POST"])
def menu():
    uid, tab = get_current_uid()
    if not uid:
        return redirect("/")

    user = get_user_by_id(uid)
    if not user:
        return redirect("/")

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
        token_value = session.get("current_token", "")

    # komunikat błędu/sukcesu z redirectów (bez ?error=... w URL)
    message = pop_menu_message(tab) or request.args.get("message", "")

    # POST – zatwierdzenie transakcji (wykorzystywane przy TPAY)
    if request.method == "POST":
        user_auth = (request.form.get("auth") or "").strip()
        print(f"DEBUG: POST na /menu - user_auth={user_auth}, token_value={token_value}")
        if token_value:
            try:
                raw = token_value.replace("TPAY:", "")
                parts = raw.split("Z")
                if len(parts) != 4:
                    message = f"Błąd: Nieprawidłowy format tokena (części: {len(parts)})"
                    print(f"DEBUG: Błędny format tokena - części: {parts}")
                else:
                    user_id, action, amount, token_auth_encoded = parts
                    token_auth = decode_auth(token_auth_encoded)
                    print(f"DEBUG: Parsowanie tokena OK - uid={user_id}, action={action}, amount={amount}, token_auth={token_auth}")
                    # amount w tokenie = ilość TCOIN, kropka zapisana jako 'X'
                    amount_str = (
                        str(amount)
                        .strip()
                        .replace("X", ".")
                        .replace(",", ".")
                    )
                    try:
                        amount = float(amount_str)
                        print(f"DEBUG: Kwota sparsowana: {amount}")
                    except ValueError:
                        message = "Błędna wartość kwoty w tokenie."
                        print(f"DEBUG: Błąd konwersji kwoty: {amount_str}")
                    else:
                        if not user_auth:
                            message = "Zły AUTH"
                            print(f"DEBUG: Brak AUTH")
                        elif not user_auth.isdigit():
                            message = "Zły AUTH"
                            print(f"DEBUG: AUTH nie jest cyfrą: {user_auth}")
                        elif user_auth != token_auth:
                            message = "Zły AUTH!"
                            print(f"DEBUG: Zły AUTH - otrzymane: {user_auth}, oczekiwane: {token_auth}")
                        else:
                            print(f"DEBUG: AUTH OK! Wykonuję transakcję...")
                            current_balance = float(user.get("balance", 0))
                            
                            if action == "0":  # Kupno TCOIN
                                new_balance = current_balance + amount
                                save_user_balance(uid, new_balance)
                                message = (
                                    f"Transakcja kupna zatwierdzona! "
                                    f"Dostałeś {amount} TCOIN. "
                                    f"Twoje nowe saldo: {new_balance} TCOIN."
                                )
                                print(f"DEBUG: Kupno OK - nowe saldo: {new_balance}")
                            else:  # Sprzedaż TCOIN
                                if current_balance < amount:
                                    message = (
                                        f"Nie masz wystarczającej ilości TCOIN! "
                                        f"Potrzeba {amount}, a masz: {current_balance} TCOIN."
                                    )
                                    print(f"DEBUG: Za mało salda")
                                else:
                                    new_balance = current_balance - amount
                                    save_user_balance(uid, new_balance)
                                    message = (
                                        f"Transakcja sprzedaży zatwierdzona! "
                                        f"Sprzedałeś {amount} TCOIN. "
                                        f"Twoje nowe saldo: {new_balance} TCOIN."
                                    )
                                    print(f"DEBUG: Sprzedaż OK - nowe saldo: {new_balance}")
                        
                        # usuwamy token tylko dla tej konkretnej karty
                        if tab and tab in tokens:
                            tokens.pop(tab, None)
                            session["tokens"] = tokens
                        session.pop("current_token", None)
                        token_value = ""
                        
                        # Odśwież dane użytkownika po transakcji
                        user = get_user_by_id(uid)
            except Exception as e:
                message = f"Błąd przy przetwarzaniu transakcji: {str(e)}"
                print(f"DEBUG: Wyjątek: {e}")
                import traceback
                traceback.print_exc()
        else:
            message = "Nie masz wygenerowanego tokena!"
            print(f"DEBUG: Brak tokena w sesji")

    current_rate = load_tbuy_rate()
    balance_tcoin = float(user.get("balance", 0) or 0)
    balance_pln = balance_tcoin * current_rate if current_rate else 0

    return render_template(
        "menu.html",
        tcoin_rate=current_rate,
        balance_pln=balance_pln,
        balance_tcoin=balance_tcoin,
        token_value=token_value,
        message=message,
        uid=uid,
        tab=tab or "",
    )

@app.route("/generate_token", methods=["POST"])
def generate_token_menu():
    uid, tab = get_current_uid()
    if not uid:
        return redirect("/")
    
    user = get_user_by_id(uid)
    if not user:
        return redirect("/")

    action = request.form["action"]
    # keep the original input to build token (convert '.' and ',' to 'X')
    amount_input = (request.form.get("amount") or "").strip()
    amount_token = amount_input.replace(" ", "").replace(".", "X").replace(",", "X")
    try:
        amount = float(amount_input.replace(",", "."))
    except ValueError:
        err = "Błędna wartość ilości (użyj liczb, np. 10 lub 10.5)."
        set_menu_message(err, tab)
        if tab:
            return redirect(f"/menu?tab={tab}")
        return redirect("/menu")

    # jeśli akcja = sprzedaż i saldo jest mniejsze niż ilość → blokada
    # pokazujemy komunikat na stronie menu (tak jak inne błędy), zamiast osobnej strony
    if action == "1" and user.get("balance", 0) < amount:
        err = "Nie masz wystarczającej ilości TCOIN, aby wygenerować token do sprzedaży!"
        set_menu_message(err, tab)
        if tab:
            return redirect(f"/menu?tab={tab}")
        return redirect("/menu")

    # obsługa prezentu (akcja 2): natychmiastowy transfer bez tokenów
    if action == "2":
        gift_code = (request.form.get("recipient_id") or "").strip()
        # format 0Z<uid>Z0
        parts = gift_code.split("Z")
        if len(parts) != 3 or parts[0] != "0" or parts[2] != "0" or not parts[1].isdigit():
            err = "Nieprawidłowy format gift ID. Użyj 0Z<id odbiorcy>Z0."
            set_menu_message(err, tab)
            if tab:
                return redirect(f"/menu?tab={tab}")
            return redirect("/menu")
        
        recipient_uid = parts[1]
        recipient = get_user_by_id(recipient_uid)
        if not recipient:
            err = "Nieznany odbiorca."
            set_menu_message(err, tab)
            if tab:
                return redirect(f"/menu?tab={tab}")
            return redirect("/menu")
        
        if user.get("balance", 0) < amount:
            err = "Nie masz wystarczającej ilości TCOIN."
            set_menu_message(err, tab)
            if tab:
                return redirect(f"/menu?tab={tab}")
            return redirect("/menu")
        
        # wykonaj transfer
        sender_balance = float(user.get("balance", 0)) - amount
        recipient_balance = float(recipient.get("balance", 0)) + amount
        
        save_user_balance(uid, sender_balance)
        save_user_balance(recipient_uid, recipient_balance)
        
        msg = f"Przekazano {amount} TCOIN do użytkownika {recipient_uid}."
        if tab:
            return redirect(f"/menu?tab={tab}&message={quote_plus(msg)}")
        return redirect(f"/menu?message={quote_plus(msg)}")

    # normalny token TPAY do kupna/sprzedaży
    token_auth = str(random.randint(1000, 9999))
    token_auth_encoded = encode_auth(token_auth)
    token = f"TPAY:{uid}Z{action}Z{amount_token}Z{token_auth_encoded}"

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

@app.route("/admin/decode_token", methods=["GET", "POST"])
def admin_decode_token():
    uid, tab = get_current_uid()
    if not uid:
        return redirect("/")
    
    user = get_user_by_id(uid)
    if not user or user.get("role") != "admin":
        return "Brak uprawnień", 403
    
    if request.method == "POST":
        token = request.form.get("token", "")
        if not token.startswith("TPAY:"):
            return render_template("admin_decode.html", tab=tab or "", error="To nie token TPAY", show_result=False)
        raw = token.replace("TPAY:", "")
        try:
            user_id, action, amount, token_auth_encoded = raw.split("Z")
        except ValueError:
            return render_template("admin_decode.html", tab=tab or "", error="Nieprawidłowy format tokena", show_result=False)

        target_user = get_user_by_id(user_id)
        username = target_user.get("username") if target_user else f"nieznany użytkownik (ID: {user_id})"

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

        token_auth = decode_auth(token_auth_encoded)

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

    user = get_user_by_id(uid)
    if not user or user.get("role") != "admin":
        return "Brak uprawnień", 403

    try:
        # Pobierz aktualny kurs
        current_rate = load_tbuy_rate()

        # losowa zmiana kursu 1–100 zł w górę lub w dół
        change_zl = random.randint(1, 100)
        direction = random.choice([-1, 1])
        new_rate = current_rate + direction * change_zl

        # nie pozwalamy spaść kursowi poniżej bazowego kursu
        if new_rate < BASE_TBUY_RATE:
            new_rate = BASE_TBUY_RATE

        today = datetime.date.today().isoformat()
        
        # Aktualizuj lub wstaw nowy kurs dla danej daty
        supabase.table("exchange_rates").upsert({
            "date": today,
            "rate": new_rate
        }, on_conflict="date").execute()
    except Exception as e:
        print(f"Błąd przy zmianie kursu: {e}")

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

    user = get_user_by_id(uid)
    if not user or user.get("role") != "admin":
        return "Brak uprawnień", 403

    try:
        today = datetime.date.today().isoformat()
        supabase.table("exchange_rates").upsert({
            "date": today,
            "rate": BASE_TBUY_RATE
        }, on_conflict="date").execute()
    except Exception as e:
        print(f"Błąd przy resetowaniu kursu: {e}")

    if tab:
        return redirect(f"/menu?tab={tab}")
    return redirect("/menu")

# ---------- WYLOGUJ ----------

@app.route("/delete_account", methods=["POST"])
def delete_account():
    uid, tab = get_current_uid()
    if not uid:
        return redirect("/")

    user = get_user_by_id(uid)
    if not user:
        return redirect("/")

    confirm_text = (request.form.get("confirm_delete") or "").strip().upper()
    if confirm_text != "USUN":
        err = "Aby usunąć konto, wpisz dokładnie: USUN"
        set_menu_message(err, tab)
        if tab:
            return redirect(f"/menu?tab={tab}")
        return redirect("/menu")

    if user.get("role") == "admin":
        err = "Konto admina nie może zostać usunięte."
        set_menu_message(err, tab)
        if tab:
            return redirect(f"/menu?tab={tab}")
        return redirect("/menu")

    try:
        supabase.table("users").delete().eq("id", int(uid)).execute()
    except Exception as e:
        print(f"Błąd przy usuwaniu konta: {e}")
        err = "Nie udało się usunąć konta."
        set_menu_message(err, tab)
        if tab:
            return redirect(f"/menu?tab={tab}")
        return redirect("/menu")

    # Wyczyść powiązania z kartami i tokenami dla usuniętego użytkownika
    tabs = session.get("tabs", {})
    tabs_to_remove = [tab_id for tab_id, tab_uid in tabs.items() if str(tab_uid) == str(uid)]
    for tab_id in tabs_to_remove:
        tabs.pop(tab_id, None)
    session["tabs"] = tabs

    tokens = session.get("tokens", {})
    for tab_id in tabs_to_remove:
        tokens.pop(tab_id, None)
    session["tokens"] = tokens

    if str(session.get("user_id")) == str(uid):
        session.pop("user_id", None)
    session.pop("current_token", None)

    return redirect("/")

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