import os
import tempfile
from pathlib import Path

TEMP = tempfile.TemporaryDirectory()
os.environ['MOMA_DB_PATH'] = str(Path(TEMP.name)/'test.sqlite3')
os.environ['MOMA_ADMIN_KEY'] = 'chiave-locale-prova'
from fastapi.testclient import TestClient
from main import app

client = TestClient(app)


def test_catalogo_eventi():
    works = client.get('/api/opere')
    assert works.status_code == 200 and len(works.json()) == 3
    assert len(client.get('/api/opere?q=Picasso').json()) == 1
    events = client.get('/api/eventi')
    assert events.status_code == 200 and len(events.json()) == 3


def test_booking_capacity_and_admin():
    booking = client.post('/api/prenotazioni', json={'nome':'Nome Test','email':'esempio@example.org','evento_id':2,'persone':6})
    assert booking.status_code == 201
    assert booking.json()['stato']=='confermata'
    second = client.post('/api/prenotazioni',json={'nome':'Altra Persona','email':'altro@example.org','evento_id':2,'persone':6})
    assert second.status_code == 201
    exceed = client.post('/api/prenotazioni',json={'nome':'Terza Persona','email':'terzo@example.org','evento_id':2,'persone':1})
    assert exceed.status_code == 409
    assert client.get('/api/admin/dashboard').status_code == 401
    stats = client.get('/api/admin/dashboard',headers={'X-Admin-Key':'chiave-locale-prova'})
    assert stats.status_code == 200 and stats.json()['persone_prenotate']==12
    all_rows=client.get('/api/admin/prenotazioni',headers={'X-Admin-Key':'chiave-locale-prova'})
    assert len(all_rows.json())==2


def test_feedback_validation():
    invalid=client.post('/api/feedback',json={'voto':7,'commento':'ottimo'})
    assert invalid.status_code==422
    valid=client.post('/api/feedback',json={'voto':5,'commento':'Esperienza di prova positiva'})
    assert valid.status_code==201


def test_admin_add_cancel():
    h={'X-Admin-Key':'chiave-locale-prova'}
    new=client.post('/api/admin/eventi',headers=h,json={'titolo':'Nuovo evento demo','data':'2027-03-01','orario':'10:00','posti_totali':15,'descrizione':'Laboratorio dimostrativo'})
    assert new.status_code==201
    rows=client.get('/api/admin/prenotazioni',headers=h).json()
    cancel=client.patch(f"/api/admin/prenotazioni/{rows[0]['id']}/annulla", headers=h)
    assert cancel.status_code==200
