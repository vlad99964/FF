from flask import Flask, render_template_string, request, redirect, session, url_for
import sqlite3, hashlib, os, glob
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "your_secret_key_here"
UPLOAD_FOLDER = "static/uploads"
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


def get_db_connection():
    conn = sqlite3.connect("ff.db", timeout=30)
    conn.row_factory = sqlite3.Row
    return conn


def login_required(func):
    from functools import wraps

    @wraps(func)
    def wrapper(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return func(*args, **kwargs)

    return wrapper

NAV_BAR = """
<div class="nav">
  <a href="javascript:history.back()">⬅ Назад</a>
  <a href="/create_request">➕ Новая заявка</a>
  <a href="/">🏠 Главная</a>
</div>
<style>
  .nav {
    position: fixed;
    bottom: 0;
    left: 0;
    width: 100%;
    background: #eee;
    border-top: 1px solid #ccc;
    display: flex;
    justify-content: space-around;
    padding: 10px;
  }
  .nav a {
    text-decoration: none;
    color: #333;
    font-weight: bold;
  }
</style>
"""

HEADER_HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <style>
    body { font-family: sans-serif; margin: 10px; padding: 0 10px 70px; /* добавлено нижнее поле */ }
    table { width: 100%; border-collapse: collapse; }
    th, td { padding: 8px; text-align: left; border-bottom: 1px solid #ddd; }
    tr.unready { background-color: #ffe5e5; }
    tr.ready { background-color: #e5ffe5; }
    tr.in_repair { background-color: #fffbe5; }
    tr.waiting_parts { background-color: #fff3e0; }
    select, button { font-size: 1rem; margin: 0.5em 0; }
  </style>
</head>
<body>
"""
FOOTER_HTML = "</body></html>"

# Маппинг числовых статусов на человекочитаемые строки
STATUS_LABELS = {
    0: "Сломан",
    1: "Исправен",
    2: "В ремонте",
    3: "Ожидает запчастей",
}

@app.route("/")
@login_required
def index():
    conn = get_db_connection()
    raw_firm = request.args.get("firm")
    raw_model = request.args.get("model")

    firm = raw_firm if raw_firm else None
    model = raw_model if raw_model else None

    firms = conn.execute(
        "SELECT DISTINCT firm FROM PrinterModels ORDER BY firm"
    ).fetchall()

    models_query = "SELECT model FROM PrinterModels"
    model_params = []
    if firm:
        models_query += " WHERE firm = ?"
        model_params.append(firm)
    models_query += " ORDER BY model"
    models = conn.execute(models_query, model_params).fetchall()

    if firm and models and raw_model is None:
        model = models[0]["model"]

    # Сортировка по приоритету: В ремонте (2), Сломан (0), Ожидает запчастей (3), Исправен (1)
    query = """
        SELECT firm, model, order_number, workable, id_priint
        FROM Print
        WHERE (? IS NULL OR firm = ?) AND (? IS NULL OR model = ?)
        ORDER BY
          CASE workable
            WHEN 2 THEN 0
            WHEN 0 THEN 1
            WHEN 3 THEN 2
            WHEN 1 THEN 3
          END,
          order_number ASC
    """
    printers = conn.execute(query, (firm, firm, model, model)).fetchall()
    conn.close()

    return render_template_string(
        HEADER_HTML + """
    <h1>ФОРМФАКТОР</h1>

    <div style="display: flex; align-items: center; justify-content: flex-start; flex-wrap: wrap; margin-bottom: 10px;">
      <form method="get" id="filter-form" style="margin-right: 20px;">
        <label>Фирма:
          <select name="firm" onchange="this.form.submit()">
            <option value="">Все</option>
            {% for f in firms %}
              <option value="{{ f.firm }}" {% if raw_firm == f.firm %}selected{% endif %}>{{ f.firm }}</option>
            {% endfor %}
          </select>
        </label>
        <input type="hidden" name="model" id="model-input" value="{{ model or '' }}">
      </form>

      {% if raw_firm and models %}
      <form method="get" id="model-filter" style="display: flex; flex-wrap: wrap; gap: 5px;">
        <input type="hidden" name="firm" value="{{ raw_firm }}">
        <input type="hidden" name="model" id="model-button-input" value="{{ model or '' }}">
        {% for m in models %}
          <button type="button"
                  class="model-toggle"
                  data-model="{{ m.model }}"
                  style="padding: 5px 10px; background-color: {% if model == m.model %}#ccc{% else %}#eee{% endif %}; border: 1px solid #999; border-radius: 6px; cursor: pointer;">
            {{ m.model }}
          </button>
        {% endfor %}
      </form>
      {% endif %}
    </div>

    <script>
      document.addEventListener('DOMContentLoaded', function () {
        document.querySelectorAll('.model-toggle').forEach(button => {
          const input = document.getElementById('model-button-input');
          const form = document.getElementById('model-filter');
          button.addEventListener('click', () => {
            const clicked = button.dataset.model;
            input.value = (clicked === input.value) ? "" : clicked;
            form.submit();
          });
        });
      });
    </script>

    {% if printers %}
    <table>
      <thead>
        <tr>
          <th>Фирма</th>
          <th>Модель</th>
          <th>Номер</th>
          <th>Статус</th>
        </tr>
      </thead>
      <tbody>
        {% for p in printers %}
        <tr class="{% if p.workable == 0 %}unready{% elif p.workable == 1 %}ready{% elif p.workable == 2 %}in_repair{% elif p.workable == 3 %}waiting_parts{% endif %}">
          <td>{{ p.firm }}</td>
          <td>{{ p.model }}</td>
          <td><a href="/requests?printer_id={{ p.id_priint }}">{{ p.order_number }}</a></td>
          <td>{{ STATUS_LABELS[p.workable] }}</td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    {% else %}
    <p>Нет данных для отображения.</p>
    {% endif %}
    """ + NAV_BAR + FOOTER_HTML,
        firms=firms,
        models=models,
        model=model,
        printers=printers,
        raw_firm=raw_firm,
        raw_model=raw_model,
        STATUS_LABELS=STATUS_LABELS
    )

@app.route("/print")
@login_required
def print():
    model_id = request.args.get("model_id")
    conn = get_db_connection()

    model_info = conn.execute(
        "SELECT Firm, Model FROM PrinterModels WHERE id_model = ?", (model_id,)
    ).fetchone()
    print = conn.execute(
        "SELECT id_printer, serial_number, order_number FROM Print WHERE model_id = ? ORDER BY order_number",
        (model_id,),
    ).fetchall()

    print_with_status = []
    broken_count = 0
    for printer in print:
        last_fix = conn.execute(
            "SELECT fixed FROM FixRequests WHERE printer_id = ? ORDER BY date_in DESC LIMIT 1",
            (printer["id_printer"],),
        ).fetchone()
        status = "❌" if last_fix and last_fix["fixed"] == 0 else ""
        if status == "❌":
            broken_count += 1
        print_with_status.append(
            {
                "id": printer["id_printer"],
                "order_number": printer["order_number"],
                "serial_number": printer["serial_number"],
                "status": status,
            }
        )

    # Сортировка: сначала неисправные, потом исправные, внутри по order_number
    print_with_status.sort(key=lambda p: (p["status"] != "❌", p["order_number"]))

    conn.close()

    return render_template_string(
        """
    <h1>{{ model_info.Firm }} {{ model_info.Model }}</h1>
    <p>Неисправных принтеров: {{ broken_count }}</p>
    <button onclick="document.querySelectorAll('.sn').forEach(e => e.style.display = e.style.display === 'none' ? 'inline' : 'none')">Показать / скрыть серийные номера</button>
    <ul>
      {% for p in print_with_status %}
        <li>#{{ p.order_number }} {{ p.status }} <span class="sn" style="display:none">(S/N: {{ p.serial_number }})</span> - <a href="/requests?printer_id={{ p.id }}">Заявки</a></li>
      {% endfor %}
    </ul>
    """,
        model_info=model_info,
        print_with_status=print_with_status,
        broken_count=broken_count,
    )


@app.route("/requests")
@login_required
def view_requests():
    printer_id = request.args.get("printer_id")
    conn = get_db_connection()
    printer = conn.execute(
        "SELECT * FROM Print WHERE id_priint = ?",
        (printer_id,),
    ).fetchone()

    requests = conn.execute(
        """
        SELECT r.id_fix, r.trouble, r.ready, r.date_in, r.date_out, u.fio AS worker_name
        FROM FixRequest r
        LEFT JOIN Users u ON r.worker_id = u.id_user
        WHERE r.printer_id = ?
        ORDER BY r.date_in DESC
        """,
        (printer_id,),
    ).fetchall()

    photo_map = {}
    for path in glob.glob(f"{UPLOAD_FOLDER}/printer_{printer_id}_*"):
        base = os.path.basename(path)
        photo_map[base] = "/" + path.replace("\\", "/")

    conn.close()
    return render_template_string(
        """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
      <meta name="viewport" content="width=device-width, initial-scale=1.0">
      <style>
        body { font-family: sans-serif; margin: 10px; padding: 0; }
        ul { padding: 0; list-style-type: none; }
        li { margin-bottom: 1em; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; }
        .text { max-width: 75%; }
        img { height: 60px; border-radius: 6px; border: 1px solid #ccc; margin-left: 10px; }
      </style>
    </head>
    <body>
    <h1>{{ printer.firm }} {{ printer.model }} №{{ printer.order_number }}</h1>
    <ul>
      {% for r in requests %}
        <li>
          <div class="text">
            [{{ '✔' if r.ready else '🛠' }}] {{ r.date_in }}:<br>
            {% if r.trouble.strip() %}{{ r.trouble }}{% else %}Пользователь {{ r.worker_name or 'неизвестно' }} не указал дефект{% endif %}
          </div>
          {% for name, path in photo_map.items() if 'printer_' + printer_id|string in name %}
            <a href="{{ path }}" target="_blank">
              <img src="{{ path }}">
            </a>
          {% endfor %}
        </li>
      {% endfor %}
    </ul>
    """
        + NAV_BAR
        + """
    </body>
    </html>
    """,
        requests=requests,
        printer=printer,
        photo_map=photo_map,
        printer_id=printer_id,
    )


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"]
        password = request.form["password"]
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()

        conn = get_db_connection()
        user = conn.execute(
            "SELECT * FROM Users WHERE username = ? AND password_hash = ?",
            (username, hashed_pw),
        ).fetchone()
        conn.close()

        if user:
            session["user_id"] = user["id_user"]
            return redirect(url_for("index"))
        else:
            return "Неверный логин или пароль"

    return render_template_string(
        """
    <form method="POST">
      <label>Username: <input type="text" name="username"></label><br>
      <label>Password: <input type="password" name="password"></label><br>
      <button type="submit">Login</button>
    </form>
    """
    )


@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        fio = request.form["fio"]
        post = request.form["post"]
        email = request.form["email"]
        username = request.form["username"]
        password = request.form["password"]
        password_hash = hashlib.sha256(password.encode()).hexdigest()

        conn = get_db_connection()

        existing = conn.execute(
            "SELECT 1 FROM Users WHERE username = ? OR email = ?", (username, email)
        ).fetchone()

        if existing:
            conn.close()
            return "Пользователь с таким именем или email уже существует."

        conn.execute(
            "INSERT INTO Users (fio, post, email, username, password_hash) VALUES (?, ?, ?, ?, ?)",
            (fio, post, email, username, password_hash),
        )
        conn.commit()
        conn.close()

        return redirect(url_for("login"))

    return render_template_string(
        HEADER_HTML
        + """
    <form method="POST">
      <label>ФИО: <input type="text" name="fio" required></label><br>
      <label>Должность: <input type="text" name="post" required></label><br>
      <label>Email: <input type="email" name="email" required></label><br>
      <label>Username: <input type="text" name="username" required></label><br>
      <label>Password: <input type="password" name="password" required></label><br>
      <button type="submit">Зарегистрироваться</button>
    </form>
    """
        + NAV_BAR
        + FOOTER_HTML
    )


from flask import request, render_template_string, session
from werkzeug.utils import secure_filename
import os, sqlite3

STATUS_LABELS = {
    0: "Сломан",
    1: "Исправен",
    2: "В ремонте",
    3: "Ожидает запчастей",
}

@app.route("/create_request", methods=["GET", "POST"])
@login_required
def create_request():
    try:
        with get_db_connection() as conn:
            firm_model_pairs = conn.execute(
                "SELECT firm, model FROM PrinterModels ORDER BY firm, model"
            ).fetchall()

            if request.method == "POST":
                firm         = request.form["firm"]
                model        = request.form["model"]
                action       = request.form["action"]        # "0","1","2","3" или "none"
                order_number = request.form["order_number"]
                serial       = request.form["serial"].strip()
                trouble      = request.form["trouble"]

                # Вставляем новую пару фирма+модель (если нужно)
                conn.execute(
                    "INSERT OR IGNORE INTO PrinterModels (firm, model) VALUES (?, ?)",
                    (firm, model),
                )

                # Ищем существующий принтер
                printer_row = conn.execute(
                    "SELECT id_priint FROM Print WHERE firm=? AND model=? AND order_number=?",
                    (firm, model, order_number),
                ).fetchone()
                if not printer_row and serial:
                    printer_row = conn.execute(
                        "SELECT id_priint FROM Print WHERE serial_number=?",
                        (serial,),
                    ).fetchone()

                if printer_row:
                    printer_id = printer_row["id_priint"]
                else:
                    # Создаём новый принтер со статусом "Сломан" (0)
                    conn.execute(
                        "INSERT INTO Print (firm, model, serial_number, order_number, workable) "
                        "VALUES (?, ?, ?, ?, 0)",
                        (firm, model, serial, order_number),
                    )
                    printer_id = conn.execute(
                        "SELECT id_priint FROM Print WHERE firm=? AND model=? AND order_number=?",
                        (firm, model, order_number),
                    ).fetchone()["id_priint"]

                # Парсим выбранный статус
                if action == "none":
                    new_status = None
                else:
                    try:
                        new_status = int(action)
                        if new_status not in (0, 1, 2, 3):
                            raise ValueError
                    except ValueError:
                        return "Неизвестное действие.", 400

                # Вставляем заявку
                conn.execute(
                    "INSERT INTO FixRequest (printer_id, worker_id, trouble, ready, date_in) VALUES "
                    "(?, ?, ?, ?, datetime('now'))",
                    (printer_id,
                     session["user_id"],
                     trouble,
                     new_status if new_status is not None else 0,
                    ),
                )

                # Обновляем статус принтера, если указано
                if new_status is not None:
                    conn.execute(
                        "UPDATE Print SET workable=? WHERE id_priint=?",
                        (new_status, printer_id),
                    )

                # Сохраняем фото, если было загружено
                if "photo" in request.files:
                    photo = request.files["photo"]
                    if photo.filename:
                        filename = secure_filename(f"printer_{printer_id}_{photo.filename}")
                        photo.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

                return redirect(url_for('index'))

    except sqlite3.IntegrityError as e:
        return f"Ошибка целостности данных: {e}", 500
    except sqlite3.OperationalError as e:
        return f"Ошибка базы данных: {e}", 500

    # 🔽 HTML-форма
    return render_template_string(
        HEADER_HTML + """
<form method="POST" enctype="multipart/form-data">
  <label>Фирма и модель:
    <select name="firm_model" required>
      {% for pair in firm_model_pairs %}
        <option value="{{pair.firm}}||{{pair.model}}">{{pair.firm}} {{pair.model}}</option>
      {% endfor %}
    </select>
  </label><br>
  <input type="hidden" name="firm">
  <input type="hidden" name="model">
  <script>
    document.addEventListener('DOMContentLoaded', () => {
      const sel = document.querySelector('select[name="firm_model"]');
      const iFirm = document.querySelector('input[name="firm"]');
      const iModel = document.querySelector('input[name="model"]');
      const upd = () => {
        const [f,m] = sel.value.split('||');
        iFirm.value = f; iModel.value = m;
      };
      sel.addEventListener('change', upd);
      upd();
    });
  </script>

  <label>Порядковый номер: <input type="number" name="order_number" required></label><br>
  <label>Серийный номер:   <input type="text"   name="serial"></label><br>
  <label>Фото:             <input type="file"   name="photo" accept="image/*" capture="environment"></label><br>

  <label>Состояние принтера:
    <select name="action">
      <option value="0">Сломан</option>
      <option value="1">Исправен</option>
      <option value="2">В ремонте</option>
      <option value="3">Ожидает запчастей</option>
      <option value="none">Без изменения</option>
    </select>
  </label><br>

  <label>Описание проблемы:<br><textarea name="trouble"></textarea></label><br>
  <button type="submit">Создать заявку</button>
</form>
""" + NAV_BAR + FOOTER_HTML,
        firm_model_pairs=firm_model_pairs,
    )




if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
