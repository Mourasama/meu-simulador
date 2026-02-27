"""
data_fetcher.py — Módulo centralizado de busca de dados de mercado.

Responsabilidades:
- Busca e sugestão de tickers (autocomplete) via yfinance
- Normalização automática de tickers da B3 (adiciona .SA)
- Busca de preço atual de ações
- Busca da taxa Selic/CDI atual via API do Banco Central do Brasil
"""

import re
import asyncio
import requests as http_requests
from typing import List, Dict, Optional
from functools import lru_cache
import yfinance as yf

_B3_PATTERN = re.compile(r'^[A-Z]{4}\d{1,2}$', re.IGNORECASE)

_selic_cache: Optional[float] = None

def normalize_ticker(ticker: str) -> str:
    """
    Normaliza um ticker para uso com yfinance.
    - Se for um ticker da B3 sem sufixo (ex: PETR4), adiciona .SA
    - Se já tiver sufixo (ex: PETR4.SA) ou for crypto (BTC/USDT), mantém como está
    """
    ticker = ticker.strip().upper()
    if not ticker:
        return ticker

    if '.' in ticker:
        return ticker

    if '/' in ticker:
        return ticker

    if _B3_PATTERN.match(ticker):
        return f"{ticker}.SA"

    return ticker

@lru_cache(maxsize=128)
def search_crypto_coingecko(query: str, max_results: int = 5) -> List[Dict[str, str]]:
    """
    Busca criptomoedas usando a API de busca do CoinGecko.
    Retorna lista de dicts com 'symbol', 'name', 'id' e 'type'.
    """
    if not query or len(query) < 2:
        return []

    try:
        url = f"https://api.coingecko.com/api/v3/search?query={query}"
        resp = http_requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            coins = data.get('coins', [])
            results = []
            for coin in coins[:max_results]:
                symbol = coin.get('symbol', '').upper()
                name = coin.get('name', '')
                cg_id = coin.get('id', '')
                results.append({
                    'symbol': symbol,
                    'name': name,
                    'id': cg_id,
                    'type': 'CRYPTOCURRENCY',
                    'exchange': 'CoinGecko'
                })
            return results
    except Exception as e:
        print(f"Erro na busca de criptos CoinGecko: {e}")
    return []

@lru_cache(maxsize=128)
def search_tickers(query: str, max_results: int = 8) -> List[Dict[str, str]]:
    """
    Busca sugestões de tickers usando yfinance e CoinGecko.
    Retorna lista de dicts com 'symbol', 'name', 'type', etc.
    """
    if not query or len(query) < 2:
        return []

    results = []

    try:
        crypto_results = search_crypto_coingecko(query, max_results=max_results)
        results.extend(crypto_results)
    except Exception:
        pass

    try:
        if hasattr(yf, 'Search'):
            search = yf.Search(query, max_results=max_results)
            quotes = getattr(search, 'quotes', []) or []
            for q in quotes:
                symbol = q.get('symbol', '')
                name = q.get('longname') or q.get('shortname') or symbol
                quote_type = q.get('quoteType', '')

                if quote_type in ('EQUITY', 'ETF', 'CRYPTOCURRENCY'):

                    if not any(r['symbol'] == symbol.upper().replace("-USD", "") for r in results):
                        results.append({
                            'symbol': symbol,
                            'name': name,
                            'exchange': q.get('exchange', ''),
                            'type': quote_type,
                        })
    except Exception as e:
        print(f"Erro na busca yfinance: {e}")

    return results[:max_results]

def get_stock_price(ticker: str) -> float:
    """
    Retorna o preço atual de uma ação/ETF.
    Normaliza o ticker automaticamente (adiciona .SA para B3).
    """
    normalized = normalize_ticker(ticker)
    try:
        t = yf.Ticker(normalized)
        hist = t.history(period="2d")
        if hist.empty:
            return 0.0
        return float(hist['Close'].iloc[-1])
    except Exception as e:
        print(f"Erro ao buscar preço de {normalized}: {e}")
        return 0.0

def get_selic_rate() -> float:
    """
    Retorna a taxa Selic Over anual atual via API do Banco Central do Brasil.
    Endpoint: https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados/ultimos/1?formato=json
    Série 11 = Taxa Selic Over (% a.a.)

    Retorna a taxa como decimal (ex: 0.1075 para 10,75% a.a.)
    Usa cache para evitar chamadas repetidas.
    """
    global _selic_cache
    if _selic_cache is not None:
        return _selic_cache

    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.11/dados/ultimos/1?formato=json"
        resp = http_requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()

            taxa_diaria_pct = float(data[0]['valor'].replace(',', '.'))
            taxa_diaria = taxa_diaria_pct / 100.0

            _selic_cache = (1 + taxa_diaria) ** 252 - 1
            return _selic_cache
    except Exception as e:
        print(f"Erro ao buscar taxa Selic: {e}")
    return 0.1275

def get_ipca_rate() -> float:
    """
    Retorna o IPCA acumulado nos últimos 12 meses via API do BCB.
    Série 433 = IPCA (% a.m.)
    Retorna taxa anual como decimal.
    """
    try:
        url = "https://api.bcb.gov.br/dados/serie/bcdata.sgs.433/dados/ultimos/12?formato=json"
        resp = http_requests.get(url, timeout=5)
        if resp.status_code == 200:
            data = resp.json()

            acumulado = 1.0
            for item in data:
                taxa_mensal = float(item['valor'].replace(',', '.')) / 100.0
                acumulado *= (1 + taxa_mensal)
            return acumulado - 1.0
    except Exception as e:
        print(f"Erro ao buscar IPCA: {e}")

    return 0.0480

def get_cumulative_factor(serie_id: int, start_date: str) -> float:
    """
    Calcula o fator de capitalização acumulado de uma série do SGS BCB
    desde start_date (YYYY-MM-DD) até a data mais recente disponível.

    serie_id 11 = Selic diária (%)
    serie_id 12 = CDI diária (%)
    serie_id 433 = IPCA mensal (%)
    """
    try:

        dt_start = start_date.split('-')
        if len(dt_start) == 3:
            formatted_start = f"{dt_start[2]}/{dt_start[1]}/{dt_start[0]}"
        else:
            formatted_start = "01/01/2015"

        import datetime
        hoje = datetime.date.today().strftime("%d/%m/%Y")

        url = f"https://api.bcb.gov.br/dados/serie/bcdata.sgs.{serie_id}/dados?formato=json&dataInicial={formatted_start}&dataFinal={hoje}"
        resp = http_requests.get(url, timeout=15)

        if resp.status_code == 200:
            data = resp.json()
            factor = 1.0
            for item in data:
                val = float(item['valor'].replace(',', '.')) / 100.0
                factor *= (1 + val)
            return factor
    except Exception as e:
        print(f"Erro ao calcular fator acumulativo da série {serie_id}: {e}")

    return 1.0

def get_crypto_price_coingecko(ticker: str) -> float:
    """
    Retorna o preço atual de uma criptomoeda via API CoinGecko.
    O ticker pode ser um símbolo (BTC), um par (BTC/USDT) ou um ID (bitcoin).
    """
    id_map = {
        'BTC': 'bitcoin', 'ETH': 'ethereum', 'SOL': 'solana', 'BNB': 'binancecoin',
        'XRP': 'ripple', 'ADA': 'cardano', 'AVAX': 'avalanche-2', 'DOT': 'polkadot',
        'LINK': 'chainlink', 'MATIC': 'polygon', 'DOGE': 'dogecoin',
    }

    clean_ticker = ticker.split('/')[0].upper()

    cg_id = id_map.get(clean_ticker)

    if not cg_id and ticker.islower() and len(ticker) > 3:
        cg_id = ticker

    if not cg_id:
        try:
            search_res = search_crypto_coingecko(clean_ticker, max_results=1)
            if search_res:
                cg_id = search_res[0]['id']
        except Exception:
            pass

    if not cg_id:
        cg_id = clean_ticker.lower()

    try:
        url = f"https://api.coingecko.com/api/v3/simple/price?ids={cg_id}&vs_currencies=usd"
        resp = http_requests.get(url, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            if cg_id in data:
                return float(data[cg_id]['usd'])
    except Exception as e:
        print(f"Erro ao buscar preço de {ticker} (ID: {cg_id}) no CoinGecko: {e}")

    try:

        name_to_symbol = {
            'BITCOIN': 'BTC', 'ETHEREUM': 'ETH', 'SOLANA': 'SOL', 'BINANCECOIN': 'BNB',
            'RIPPLE': 'XRP', 'CARDANO': 'ADA', 'AVALANCHE': 'AVAX', 'POLKADOT': 'DOT',
            'CHAINLINK': 'LINK', 'POLYGON': 'MATIC', 'DOGECOIN': 'DOGE'
        }
        mapped_symbol = name_to_symbol.get(clean_ticker, clean_ticker)
        yf_ticker = f"{mapped_symbol}-USD"
        t = yf.Ticker(yf_ticker)
        hist = t.history(period="1d")
        if not hist.empty:
            return float(hist['Close'].iloc[-1])
    except Exception:
        pass

    return 0.0

def clear_selic_cache():
    """Limpa o cache da taxa Selic (útil para testes)."""
    global _selic_cache
    _selic_cache = None
