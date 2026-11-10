"""MoMA Digital Experience: prototipo didattico indipendente, non affiliato a MoMA."""
from __future__ import annotations

import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator

ROOT = Path(__file__).resolve().parent
DB_PATH = Path(os.getenv('MOMA_DB_PATH', ROOT / 'moma_demo.sqlite3'))
ADMIN_KEY = os.getenv('MOMA_ADMIN_KEY', '')
app = FastAPI(title='MoMA Digital Experience - Prototipo didattico', version='1.0.0')
app.mount('/static', StaticFiles(directory=ROOT / 'static'), name='static')


@contextmanager
def conn():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    database = sqlite3.connect(DB_PATH, timeout=10)
    database.row_factory = sqlite3.Row
    database.execute('PRAGMA foreign_keys=ON')
    try:
        yield database
        database.commit()
    except Exception:
        database.rollback()
        raise
    finally:
        database.close()


def init_db():
    with conn() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS opere (
          id INTEGER PRIMARY KEY, titolo TEXT NOT NULL, artista TEXT NOT NULL,
          anno TEXT NOT NULL, categoria TEXT NOT NULL, url_fonte TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS eventi (
          id INTEGER PRIMARY KEY, titolo TEXT NOT NULL, data TEXT NOT NULL,
          orario TEXT NOT NULL, posti_totali INTEGER NOT NULL CHECK (posti_totali > 0),
          descrizione TEXT NOT NULL, UNIQUE(titolo, data, orario)
        );
        CREATE TABLE IF NOT EXISTS visitatori (
          id INTEGER PRIMARY KEY, nome TEXT NOT NULL, email TEXT NOT NULL UNIQUE
        );
        CREATE TABLE IF NOT EXISTS prenotazioni (
          id INTEGER PRIMARY KEY, evento_id INTEGER NOT NULL REFERENCES eventi(id),
          visitatore_id INTEGER NOT NULL REFERENCES visitatori(id),
          persone INTEGER NOT NULL CHECK (persone BETWEEN 1 AND 6),
          stato TEXT NOT NULL DEFAULT 'confermata' CHECK (stato IN ('confermata','annullata')),
          creato_il TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS feedback (
          id INTEGER PRIMARY KEY, voto INTEGER NOT NULL CHECK (voto BETWEEN 1 AND 5),
          commento TEXT NOT NULL, creato_il TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        ''')
        if not db.execute('SELECT 1 FROM opere LIMIT 1').fetchone():
            db.executemany('INSERT INTO opere(id,titolo,artista,anno,categoria,url_fonte) VALUES(?,?,?,?,?,?)', [
                (1, 'Les Demoiselles d’Avignon', 'Pablo Picasso', '1907', 'Pittura', 'https://www.moma.org/collection/works/79766'),
                (2, 'The Persistence of Memory', 'Salvador Dalí', '1931', 'Pittura', 'https://www.moma.org/collection/works/79018'),
                (3, "Campbell’s Soup Cans", 'Andy Warhol', '1962', 'Pittura', 'https://www.moma.org/collection/works/79809'),
            ])
        if not db.execute('SELECT 1 FROM eventi LIMIT 1').fetchone():
            # Le date sono dimostrative: sono eventi inventati per il prototipo.
            db.executemany('INSERT INTO eventi(titolo,data,orario,posti_totali,descrizione) VALUES(?,?,?,?,?)', [
                ('Percorso introduttivo all’arte moderna', '2027-02-15', '10:30', 20, 'Visita dimostrativa con prenotazione di posti.'),
                ('Dal cubismo alla Pop Art', '2027-02-16', '14:00', 12, 'Percorso simulato per piccoli gruppi.'),
                ('Collezioni e nuovi linguaggi', '2027-02-17', '11:00', 16, 'Attività culturale di esempio.'),
            ])


init_db()


class PrenotazioneIn(BaseModel):
    nome: str = Field(min_length=2, max_length=80)
    email: str = Field(min_length=5, max_length=120)
    evento_id: int = Field(gt=0)
    persone: int = Field(ge=1, le=6)

    @field_validator('email')
    @classmethod
    def valid_email(cls, value):
        value = value.strip().lower()
        if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+', value):
            raise ValueError('Indirizzo email non valido')
        return value

    @field_validator('nome')
    @classmethod
    def valid_name(cls, value):
        value = value.strip()
        if len(value) < 2:
            raise ValueError('Inserire nome e cognome')
        return value


class FeedbackIn(BaseModel):
    voto: int = Field(ge=1, le=5)
    commento: str = Field(min_length=4, max_length=500)


class EventoIn(BaseModel):
    titolo: str = Field(min_length=4, max_length=120)
    data: date
    orario: str = Field(pattern=r'^([01]\d|2[0-3]):[0-5]\d$')
    posti_totali: int = Field(ge=1, le=500)
    descrizione: str = Field(min_length=5, max_length=500)


def admin_auth(x_admin_key: Annotated[str | None, Header()] = None):
    import secrets
    if not ADMIN_KEY or not x_admin_key or not secrets.compare_digest(ADMIN_KEY, x_admin_key):
        raise HTTPException(status_code=401, detail='Chiave di amministrazione assente o errata')


@app.get('/', include_in_schema=False)
def homepage():
    return FileResponse(ROOT / 'static' / 'index.html')


@app.get('/api/opere')
def opere(q: str = Query('', max_length=90), categoria: str = Query('', max_length=40)):
    with conn() as db:
        data = db.execute('''SELECT * FROM opere WHERE (titolo LIKE ? OR artista LIKE ?) AND categoria LIKE ? ORDER BY artista''',
                          (f'%{q}%', f'%{q}%', f'%{categoria}%')).fetchall()
        return [dict(r) for r in data]


@app.get('/api/eventi')
def eventi():
    with conn() as db:
        rows = db.execute('''SELECT e.*, e.posti_totali - COALESCE(SUM(CASE WHEN p.stato='confermata' THEN p.persone ELSE 0 END),0) AS disponibili
          FROM eventi e LEFT JOIN prenotazioni p ON p.evento_id=e.id GROUP BY e.id ORDER BY e.data,e.orario''').fetchall()
        return [dict(r) for r in rows]


@app.post('/api/prenotazioni', status_code=201)
def prenota(data: PrenotazioneIn):
    with conn() as db:
        # Transazione esplicita: controllo dei posti e inserimento nella stessa unità di lavoro.
        db.execute('BEGIN IMMEDIATE')
        evento = db.execute('SELECT * FROM eventi WHERE id=?', (data.evento_id,)).fetchone()
        if evento is None:
            raise HTTPException(status_code=404, detail='Evento non trovato')
        occupati = db.execute('SELECT COALESCE(SUM(persone),0) FROM prenotazioni WHERE evento_id=? AND stato=?',
                              (data.evento_id, 'confermata')).fetchone()[0]
        if data.persone > evento['posti_totali'] - occupati:
            raise HTTPException(status_code=409, detail='Posti insufficienti')
        db.execute('INSERT INTO visitatori(nome,email) VALUES(?,?) ON CONFLICT(email) DO UPDATE SET nome=excluded.nome',
                   (data.nome, data.email))
        visitatore = db.execute('SELECT id FROM visitatori WHERE email=?', (data.email,)).fetchone()[0]
        cur = db.execute('INSERT INTO prenotazioni(evento_id,visitatore_id,persone) VALUES(?,?,?)',
                         (data.evento_id, visitatore, data.persone))
        return {'id': cur.lastrowid, 'stato': 'confermata', 'evento': evento['titolo'], 'persone': data.persone}


@app.post('/api/feedback', status_code=201)
def feedback(data: FeedbackIn):
    with conn() as db:
        cur = db.execute('INSERT INTO feedback(voto,commento) VALUES(?,?)', (data.voto, data.commento.strip()))
        return {'id': cur.lastrowid, 'ricevuto': True}


@app.get('/api/admin/dashboard', dependencies=[Depends(admin_auth)])
def dashboard():
    with conn() as db:
        return {
            'prenotazioni_confermate': db.execute("SELECT COUNT(*) FROM prenotazioni WHERE stato='confermata'").fetchone()[0],
            'persone_prenotate': db.execute("SELECT COALESCE(SUM(persone),0) FROM prenotazioni WHERE stato='confermata'").fetchone()[0],
            'eventi': db.execute('SELECT COUNT(*) FROM eventi').fetchone()[0],
            'feedback': db.execute('SELECT COUNT(*) FROM feedback').fetchone()[0],
            'voto_medio': db.execute('SELECT ROUND(AVG(voto),2) FROM feedback').fetchone()[0],
        }


@app.get('/api/admin/prenotazioni', dependencies=[Depends(admin_auth)])
def prenotazioni_admin():
    with conn() as db:
        rows = db.execute('''SELECT p.id, p.persone, p.stato, p.creato_il, v.nome, v.email, e.titolo AS evento, e.data
         FROM prenotazioni p JOIN visitatori v ON p.visitatore_id=v.id JOIN eventi e ON p.evento_id=e.id
         ORDER BY p.creato_il DESC''').fetchall()
        return [dict(r) for r in rows]


@app.get('/api/admin/feedback', dependencies=[Depends(admin_auth)])
def feedback_admin():
    with conn() as db:
        return [dict(r) for r in db.execute('SELECT id, voto, commento, creato_il FROM feedback ORDER BY id DESC').fetchall()]


@app.post('/api/admin/eventi', status_code=201, dependencies=[Depends(admin_auth)])
def crea_evento(data: EventoIn):
    with conn() as db:
        try:
            cur = db.execute('INSERT INTO eventi(titolo,data,orario,posti_totali,descrizione) VALUES(?,?,?,?,?)',
                             (data.titolo, data.data.isoformat(), data.orario, data.posti_totali, data.descrizione))
        except sqlite3.IntegrityError:
            raise HTTPException(status_code=409, detail='Evento già presente')
        return {'id': cur.lastrowid, 'creato': True}


@app.patch('/api/admin/prenotazioni/{prenotazione_id}/annulla', dependencies=[Depends(admin_auth)])
def annulla(prenotazione_id: int):
    with conn() as db:
        res = db.execute('UPDATE prenotazioni SET stato=? WHERE id=? AND stato=?',
                         ('annullata', prenotazione_id, 'confermata'))
        if res.rowcount == 0:
            raise HTTPException(status_code=404, detail='Prenotazione non attiva')
        return {'annullata': True}
