import sys
import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List, Dict, Optional, Literal
import numpy as np
# Adiciona a raiz do projeto ao sys.path para evitar problemas de importação
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.models import StockAsset, CryptoAsset, FixedIncomeAsset
from backend.analytics import Portfolio, ScenarioSimulator
from backend import database as db

app = FastAPI(title="Simulador de Carteira Financeira")

# --- Pydantic Models ---
class AssetConfig(BaseModel):
    type: Literal['stock', 'crypto', 'fixed_income']
    ticker: str
    quantity: float
    purchase_price: Optional[float] = 0.0
    purchase_date: Optional[str] = None  # YYYY-MM-DD — usado para calculo pro-rata de RF

    fixed_income_rate: Optional[float] = 0.0
    fixed_income_maturity: Optional[str] = None
    fixed_income_type: Optional[str] = None  # 'PRE', 'CDI', 'IPCA+'

class PortfolioRequest(BaseModel):
    assets: List[AssetConfig]

class ScenarioRequest(BaseModel):
    assets: List[AssetConfig]
    shock_factor: str
    shock_magnitude: float

class SaveAssetRequest(BaseModel):
    portfolio_name: str = "Principal"
    user_email: Optional[str] = None
    asset: AssetConfig

class AuthRequest(BaseModel):
    email: str
    password: str

# --- Helper Factory ---
def create_asset_from_config(config: AssetConfig):
    if config.type == 'stock':
        return StockAsset(
            ticker=config.ticker,
            name=config.ticker,
            quantity=config.quantity,
            purchase_price=config.purchase_price or 0.0,
        )
    elif config.type == 'crypto':
        return CryptoAsset(
            ticker=config.ticker,
            name=config.ticker,
            quantity=config.quantity,
            purchase_price=config.purchase_price or 0.0,
        )
    elif config.type == 'fixed_income':
        # capital_inicial = preco_compra * quantidade (valor total investido)
        capital = (config.purchase_price or 0.0) * config.quantity
        return FixedIncomeAsset(
            name=config.ticker,
            quantity=config.quantity,
            rate=config.fixed_income_rate or 0.0,
            maturity_date=config.fixed_income_maturity,
            type=config.fixed_income_type or 'CDI',
            purchase_price=config.purchase_price or 0.0,
            capital_inicial=capital if capital > 0 else None,
            purchase_date=config.purchase_date,  # pro-rata desde data de compra
        )
    raise ValueError("Tipo de ativo invalido")

# --- Endpoints ---

@app.get("/tickers/search")
def search_tickers_endpoint(q: str, max_results: int = 8):
    """Busca sugestoes de tickers para autocomplete via yfinance."""
    from data_fetcher import search_tickers as _search
    if not q or len(q) < 2:
        return []
    return _search(q, max_results=max_results)

@app.post("/portfolio/calculate")
async def calculate_portfolio(request: PortfolioRequest):
    portfolio = Portfolio()
    for config in request.assets:
        try:
            asset = create_asset_from_config(config)
            portfolio.add_asset(asset)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    total_val = await portfolio.get_total_value()
    allocation = await portfolio.get_allocation()
    positions = await portfolio.get_detailed_positions()

    return {
        "total_value": total_val,
        "allocation": allocation,
        "positions": positions,
    }

@app.post("/portfolio/simulate")
async def simulate_portfolio(request: ScenarioRequest):
    portfolio = Portfolio()
    for config in request.assets:
        try:
            asset = create_asset_from_config(config)
            portfolio.add_asset(asset)
        except Exception as e:
            raise HTTPException(status_code=400, detail=str(e))

    sim_value = await ScenarioSimulator.simulate_scenario(
        portfolio, request.shock_factor, request.shock_magnitude
    )
    return {"simulated_value": sim_value}

# --- Persistence Endpoints ---

@app.post("/auth/register")
def register_user(request: AuthRequest):
    success = db.create_user(request.email, request.password)
    if success:
        return {"message": "Usuário criado com sucesso!"}
    raise HTTPException(status_code=400, detail="E-mail já está em uso.")

@app.post("/auth/login")
def login_user(request: AuthRequest):
    success = db.verify_user(request.email, request.password)
    if success:
        return {"message": "Login realizado com sucesso!"}
    raise HTTPException(status_code=401, detail="Credenciais inválidas.")

@app.get("/db/portfolios")
def get_portfolios_list(user_email: Optional[str] = None):
    return {"portfolios": db.get_portfolios(user_email)}

@app.get("/db/portfolio")
def get_saved_portfolio(name: str = "Principal", user_email: Optional[str] = None):
    return db.get_portfolio(name, user_email)

@app.post("/db/asset")
def save_asset(request: SaveAssetRequest):
    asset_dict = request.asset.model_dump()
    asset_dict["portfolio_name"] = request.portfolio_name
    asset_id = db.add_asset(asset_dict, request.user_email)
    return {"id": asset_id, "message": f"Ativo salvo na carteira {request.portfolio_name}"}

@app.delete("/db/asset/{asset_id}")
def delete_asset(asset_id: int, user_email: Optional[str] = None):
    db.remove_asset(asset_id, user_email)
    return {"message": "Ativo removido"}

@app.delete("/db/portfolio")
def clear_saved_portfolio(name: str = "Principal", user_email: Optional[str] = None):
    db.clear_portfolio(name, user_email)
    return {"message": f"Carteira {name} limpa"}

@app.get("/health")
def health():
    return {"status": "ok"}
