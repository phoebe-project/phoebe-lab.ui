from fastapi import FastAPI
from api.routes import session, dash

app = FastAPI()
app.include_router(session.router)
app.include_router(dash.router)
