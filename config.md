# Konfiguracja T-Coin 2.0 z Supabase

Aplikacja T-Coin 2.0 została zmodernizowana do używania **Supabase** zamiast plików JSON.

## 📋 Wymagania Wstępne

- Python 3.9+
- Konto na [Supabase](https://supabase.com) (darmowe)
- Git (opcjonalnie)

## 🚀 Szybki Start

### 1. Tworzenie Projektu na Supabase

#### a) Zarejestruj się na Supabase
1. Przejdź na [supabase.com](https://supabase.com)
2. Kliknij "Sign Up" i utwórz konto (możesz użyć GitHub)
3. Potwierdź email

#### b) Utwórz nowy projekt
1. Kliknij "New project" lub "Create a new project"
2. Nadaj projektowi nazwę: `t-coin` (lub inną)
3. Ustaw hasło do bazy danych (zapamiętaj je!)
4. Wybierz region (np. Europe - idealne dla Polski)
5. Kliknij "Create new project"
6. Czekaj na inicjalizację (2-3 minuty)

#### c) Skopiuj dane dostępowe
1. Otwórz projekt
2. Przejdź do **Settings** → **API** (lub Database Settings)
3. Skopiuj:
   - **Project URL** (np. `https://xxxxx.supabase.co`)
   - **anon public** API Key

### 2. Tworzenie Tabel w Bazie Danych

Przejdź do sekcji **SQL Editor** w Supabase i wykonaj poniższe kwerendy SQL:

#### Tabela `users`

```sql
create table users (
  id bigserial primary key,
  username text unique not null,
  password text not null,
  balance float default 0,
  role text default 'user',
  created_at timestamp default now()
);
```

#### Tabela `exchange_rates`

```sql
create table exchange_rates (
  id bigserial primary key,
  date date unique not null,
  rate float not null,
  created_at timestamp default now()
);
```

### 3. Tworzenie Administratora (Opcjonalne)

Aby utworzyć konto admina, wykonaj w SQL Editorie:

```sql
insert into users (username, password, role, balance) 
values ('admin', 'admin123', 'admin', 1000);
```

⚠️ **Zmień hasło admina na bezpieczne!** W prodakcji zawsze używaj haseł zahashowanych.

### 4. Konfiguracja Aplikacji Flask

#### a) Utwórz plik `.env` w głównym katalogu projektu

Skopiuj poniższy template i uzupełnij swoimi danymi z Supabase:

```env
# Supabase Configuration
SUPABASE_URL=https://xxxxx.supabase.co
SUPABASE_KEY=eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...

# Flask Configuration
SECRET_KEY=tajnyklucz123
FLASK_DEBUG=True
PORT=5000
```

**Gdzie wziąć te wartości?**
- `SUPABASE_URL`: Z Settings → API → Project URL
- `SUPABASE_KEY`: Z Settings → API → anon public
- `SECRET_KEY`: Dowolny losowy tekst (w prodakcji użyj `python -c "import secrets; print(secrets.token_hex(16))"`)

#### b) Zainstaluj zależności

```bash
pip install -r requirements.txt
```

Jeśli `requirements.txt` nie istnieje, uruchom:

```bash
pip install flask supabase python-dotenv
```

### 5. Uruchomienie Aplikacji

```bash
python main.py
```

Aplikacja powinna być dostępna na: **http://localhost:5000**

## 📚 Struktura Bazy Danych

### Tabela `users`

| Kolumna | Typ | Opis |
|---------|-----|------|
| `id` | bigserial | Unikalny ID użytkownika (klucz główny) |
| `username` | text | Nazwa użytkownika (unikalna) |
| `password` | text | Hasło (plaintext - do zamiany na hash!) |
| `balance` | float | Ilość TCOIN |
| `role` | text | `'user'` lub `'admin'` |
| `created_at` | timestamp | Data rejestracji |

### Tabela `exchange_rates`

| Kolumna | Typ | Opis |
|---------|-----|------|
| `id` | bigserial | Unikalny ID rekordu |
| `date` | date | Data kursu (unikalna) |
| `rate` | float | Kurs TCOIN w PLN |
| `created_at` | timestamp | Data utworzenia rekordu |

## 🔐 Bezpieczeństwo

⚠️ **WAŻNE**: Aktualna wersja przechowuje hasła w **plaintext**. Do produkcji:

1. **Zainstaluj bibliotekę do hashowania haseł:**
   ```bash
   pip install werkzeug
   ```

2. **Zmodyfikuj aplikację**, aby hashować hasła:
   ```python
   from werkzeug.security import generate_password_hash, check_password_hash
   
   # Przy rejestracji:
   hashed = generate_password_hash(password)
   
   # Przy logowaniu:
   check_password_hash(hashed_password, user_password)
   ```

3. **Użyj zmiennej SECRET_KEY** o dużej entropii w prodakcji:
   ```bash
   python -c "import secrets; print(secrets.token_hex(32))"
   ```

4. **Włącz HTTPS** na serwerze produkcyjnym

5. **Ustaw Row Level Security (RLS)** w Supabase:
   ```sql
   alter table users enable row level security;
   alter table exchange_rates enable row level security;
   ```

## 🧪 Testowanie Połączenia

Aby sprawdzić, czy aplikacja poprawnie łączy się z Supabase:

1. Uruchom aplikację: `python main.py`
2. Przejdź na http://localhost:5000
3. Zarejestruj nowego użytkownika
4. Sprawdź w Supabase → SQL Editor, czy użytkownik pojawił się w tabeli `users`

```sql
select * from users;
```

## 📋 Zmienne Środowiskowe

| Zmienna | Wymagana | Opis |
|---------|----------|------|
| `SUPABASE_URL` | ✅ | URL do projektu Supabase |
| `SUPABASE_KEY` | ✅ | Public API Key z Supabase |
| `SECRET_KEY` | ❌ | Klucz sesji Flask (default: `tajnyklucz123`) |
| `FLASK_DEBUG` | ❌ | Debug mode (`True`/`False`) |
| `PORT` | ❌ | Port aplikacji (default: `5000`) |

## 🚢 Deployment na Heroku / Railway

### Railway.app (Rekomendowane)

1. Utwórz konto na [railway.app](https://railway.app)
2. Połącz GitHub (push kod do GitHub)
3. Utwórz nowy projekt → Select from GitHub
4. Dodaj zmienne środowiskowe w Railway Dashboard:
   - `SUPABASE_URL`
   - `SUPABASE_KEY`
   - `SECRET_KEY`
5. Deploy!

### Heroku

1. Zainstaluj [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli)
2. Zaloguj się: `heroku login`
3. Utwórz aplikację: `heroku create t-coin-app`
4. Ustaw zmienne: `heroku config:set SUPABASE_URL=... SUPABASE_KEY=...`
5. Push: `git push heroku main`

## 🐛 Rozwiązywanie Problemów

### "ModuleNotFoundError: No module named 'supabase'"
```bash
pip install supabase python-dotenv
```

### "SUPABASE_URL i SUPABASE_KEY muszą być ustawione"
Sprawdź, czy plik `.env` istnieje i zawiera poprawne wartości.

### "Connection refused"
- Czy Supabase projekt jest aktywny? Sprawdź w Supabase dashboard
- Czy SUPABASE_URL jest poprawny?

### "relation 'users' does not exist"
Wykonaj ponownie kwerendy SQL do tworzenia tabel w SQL Editorie Supabase.

### Hasła nie działają przy logowaniu
Pewnie użyłeś innego hasła niż `admin123` dla admina. Sprawdź bazę:
```sql
select username, password from users;
```

## 📞 Wsparcie

Dokumentacja Supabase: [supabase.com/docs](https://supabase.com/docs)

## ✨ Co Się Zmieniło

- ✅ Zastąpione: `users.json` → Tabela `users` w Supabase
- ✅ Zastąpione: `tbuy_rate.json` → Tabela `exchange_rates` w Supabase
- ✅ Dodane: Biblioteka `supabase-py` dla komunikacji z API
- ✅ Dodane: Plik `.env` dla konfiguracji
- ✅ Zachowane: Cała logika biznesowa aplikacji
- ✅ Zachowane: Wszystkie route'y i funkcje

## 🎯 Następne Kroki

1. **Hashowanie haseł** - Zamień plaintext na bcrypt/argon2
2. **Walidacja danych** - Dodaj frontend i backend validation
3. **Backup bazy** - Ustaw daily backups w Supabase
4. **Monitoring** - Dodaj logging i error tracking
5. **SSL/HTTPS** - Włącz szyfrowanie w produkcji
