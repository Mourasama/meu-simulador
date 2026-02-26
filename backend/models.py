from abc import ABC, abstractmethod
from typing import Dict, Any, Optional
from datetime import datetime
import pandas as pd
import numpy as np
import yfinance as yf
import ccxt.async_support as ccxt
from scipy.stats import norm
from backend.data_fetcher import normalize_ticker, get_selic_rate, get_ipca_rate, get_crypto_price_coingecko


class Asset(ABC):
    def __init__(self, ticker: str, name: str, quantity: float = 1.0, purchase_price: float = 0.0):
        self.ticker = ticker
        self.name = name
        self.quantity = quantity
        self.purchase_price = purchase_price  # Preço unitário de compra (ou capital inicial para RF)

    @abstractmethod
    async def get_price(self) -> float:
        """Retorna o preço atual unitário do ativo."""
        pass

    def get_profit_loss(self, current_price: float) -> float:
        """Retorna o Lucro/Prejuízo total da posição."""
        return (current_price - self.purchase_price) * self.quantity

    @abstractmethod
    async def get_daily_return(self) -> float:
        """Retorna o retorno diário mais recente."""
        pass

    @abstractmethod
    async def get_risk_metrics(self) -> Dict[str, float]:
        """Retorna métricas de risco como Volatilidade, VaR."""
        pass

    def get_position_value(self, price: float) -> float:
        return price * self.quantity


class StockAsset(Asset):
    def __init__(self, ticker: str, name: str, quantity: float = 1.0, purchase_price: float = 0.0):
        # Normaliza o ticker automaticamente (adiciona .SA para B3)
        normalized = normalize_ticker(ticker)
        super().__init__(normalized, name or normalized, quantity, purchase_price)
        self._ticker_obj = yf.Ticker(self.ticker)
        self._history = None

    async def _fetch_history(self):
        if self._history is None:
            import asyncio
            loop = asyncio.get_event_loop()
            self._history = await loop.run_in_executor(
                None, lambda: self._ticker_obj.history(period="5d")
            )
        return self._history

    async def get_price(self) -> float:
        hist = await self._fetch_history()
        if hist.empty:
            return 0.0
        return float(hist['Close'].iloc[-1])

    async def get_daily_return(self) -> float:
        hist = await self._fetch_history()
        if len(hist) < 2:
            return 0.0
        return float(hist['Close'].pct_change().iloc[-1])

    async def get_risk_metrics(self) -> Dict[str, float]:
        import asyncio
        loop = asyncio.get_event_loop()
        hist_1y = await loop.run_in_executor(
            None, lambda: self._ticker_obj.history(period="1y")
        )
        if hist_1y.empty:
            return {"volatilidade": 0.0}
        returns = hist_1y['Close'].pct_change().dropna()
        vol = float(returns.std() * np.sqrt(252))
        return {"volatilidade": vol}


class CryptoAsset(Asset):
    def __init__(self, ticker: str, name: str, quantity: float = 1.0,
                 purchase_price: float = 0.0, exchange_id: str = 'binance'):
        # ticker pode ser um ID (ex: bitcoin) ou Símbolo (ex: BTC)
        super().__init__(ticker, name, quantity, purchase_price)
        self.raw_identifier = ticker # Mantém o ID do CoinGecko se vier de lá
        self.exchange_id = exchange_id
        self.exchange = getattr(ccxt, exchange_id)()

    async def get_price(self) -> float:
        import asyncio
        loop = asyncio.get_event_loop()
        price = 0.0
        try:
            # Tenta buscar pelo ID/Símbolo no CoinGecko
            price = await loop.run_in_executor(
                None, get_crypto_price_coingecko, self.raw_identifier
            )
        except Exception as e:
            print(f"Erro ao buscar preço no CoinGecko (task): {e}")

        if price > 0:
            return price
        
        # Fallback para ccxt ou yfinance
        try:
            # Aqui precisamos do Símbolo. Se self.raw_identifier for o nome longo,
            # o ccxt vai falhar. Na busca do frontend, nós passamos o símbolo no ticker.
            symbol = self.raw_identifier.upper()
            if "/" not in symbol:
                symbol = f"{symbol}/USDT"
                
            ticker_data = await self.exchange.fetch_ticker(symbol)
            return float(ticker_data['last'])
        except Exception:
            return 0.0
        finally:
            await self.exchange.close()

    async def get_daily_return(self) -> float:
        try:
            ohlcv = await self.exchange.fetch_ohlcv(self.ticker, timeframe='1d', limit=2)
            if len(ohlcv) < 2:
                return 0.0
            return (ohlcv[-1][4] - ohlcv[-2][4]) / ohlcv[-2][4]
        except Exception:
            return 0.0
        finally:
            await self.exchange.close()

    async def get_risk_metrics(self) -> Dict[str, float]:
        try:
            ohlcv = await self.exchange.fetch_ohlcv(self.ticker, timeframe='1d', limit=365)
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            returns = df['close'].pct_change().dropna()
            vol = float(returns.std() * np.sqrt(365))
            return {"volatilidade": vol}
        except Exception:
            return {"volatilidade": 0.0}
        finally:
            await self.exchange.close()


class FixedIncomeAsset(Asset):
    """
    Ativo de Renda Fixa com cálculo de valor acumulado pro-rata die.

    O 'purchase_price' aqui representa o CAPITAL INICIAL investido (valor total, não unitário).
    O 'quantity' é mantido como 1.0 por padrão para simplificar (o capital já é o valor total).

    Tipos suportados:
    - 'CDI': Capital × (1 + taxa_CDI_diária)^dias_corridos
    - 'PRE': Capital × (1 + taxa_anual)^(dias/252)
    - 'IPCA+': Capital × (1 + taxa_real + IPCA)^(dias/252) — simplificado
    """

    def __init__(self, name: str, quantity: float,
                 rate: float, maturity_date: str, type: str,
                 capital_inicial: float = None,
                 purchase_date: str = None,
                 purchase_price: float = 0.0,
                 current_market_rate: float = None):
        """
        Args:
            name: Nome do ativo (ex: 'Tesouro Selic 2029')
            quantity: Mantido para compatibilidade (use 1.0 para RF com capital_inicial)
            rate: Taxa contratada (decimal). Para CDI: percentual do CDI (ex: 1.10 = 110% CDI)
            maturity_date: Data de vencimento (YYYY-MM-DD)
            type: 'CDI', 'PRE' ou 'IPCA+'
            capital_inicial: Capital total investido (R$). Se None, usa purchase_price * quantity
            purchase_date: Data de compra (YYYY-MM-DD). Se None, usa hoje (sem rendimento)
            purchase_price: Preço de compra unitário (mantido para compatibilidade)
            current_market_rate: Taxa de mercado atual para MtM (PRE). Se None, usa rate.
        """
        super().__init__(name, name, quantity, purchase_price)
        self.rate = rate
        self.maturity = datetime.strptime(maturity_date, "%Y-%m-%d")
        self.type = type
        self.current_market_rate = current_market_rate if current_market_rate else rate

        # Capital inicial: preferência para capital_inicial, senão purchase_price * quantity
        if capital_inicial and capital_inicial > 0:
            self.capital_inicial = capital_inicial
        elif purchase_price > 0:
            self.capital_inicial = purchase_price * quantity
        else:
            self.capital_inicial = 1000.0 * quantity  # fallback

        # Data de compra para cálculo pro-rata
        if purchase_date:
            try:
                self.purchase_date = datetime.strptime(purchase_date, "%Y-%m-%d")
            except ValueError:
                self.purchase_date = datetime.now()
        else:
            self.purchase_date = datetime.now()

    def _dias_corridos(self) -> int:
        """Retorna o número de dias corridos desde a compra até hoje."""
        hoje = datetime.now()
        delta = hoje - self.purchase_date
        return max(0, delta.days)

    async def get_price(self) -> float:
        """
        Retorna o valor acumulado LÍQUIDO da posição (capital + juros - impostos).
        """
        hoje = datetime.now()
        dias_corridos = (hoje - self.purchase_date).days
        
        # Se comprou hoje, o valor bruto é exatamente o capital inicial
        if dias_corridos <= 0:
            return self.capital_inicial / self.quantity

        p_date_str = self.purchase_date.strftime("%Y-%m-%d")

        if self.type == 'CDI':
            # Fator acumulado do CDI (série 12) desde a compra
            from backend.data_fetcher import get_cumulative_factor
            import asyncio
            loop = asyncio.get_event_loop()
            factor = await loop.run_in_executor(None, get_cumulative_factor, 12, p_date_str)
            
            # Se o usuário contratou 110% do CDI, o rendimento é (fa - 1) * 1.1 + 1
            rendimento_bruto = (factor - 1) * self.rate
            valor_gross = self.capital_inicial * (1 + rendimento_bruto)

        elif self.type == 'PRE':
            # Base 252 dias úteis (aproximadamente 21 dias úteis por mês)
            dias_uteis = int(dias_corridos * (252/365))
            valor_gross = self.capital_inicial * ((1 + self.rate) ** (dias_uteis / 252))

        elif self.type == 'IPCA+':
            from backend.data_fetcher import get_cumulative_factor
            import asyncio
            loop = asyncio.get_event_loop()
            
            fator_ipca = await loop.run_in_executor(None, get_cumulative_factor, 433, p_date_str)
            dias_uteis = int(dias_corridos * (252/365))
            fator_juros = (1 + self.rate) ** (dias_uteis / 252)
            
            valor_gross = self.capital_inicial * fator_ipca * fator_juros
        else:
            valor_gross = self.capital_inicial

        # --- Cálculo de Impostos (IR e IOF) ---
        profit = valor_gross - self.capital_inicial
        if profit > 0:
            # IOF (apenas se < 30 dias)
            iof_rate = self._get_iof_rate(dias_corridos)
            iof_tax = profit * iof_rate
            remaining_profit = profit - iof_tax
            
            # IR regressivo sobre o que sobrou após IOF
            ir_rate = self._get_ir_rate(dias_corridos)
            ir_tax = remaining_profit * ir_rate
            
            valor_net = valor_gross - iof_tax - ir_tax
        else:
            valor_net = valor_gross

        return valor_net / self.quantity

    def _get_ir_rate(self, days: int) -> float:
        """Tabela regressiva de IR para Renda Fixa."""
        if days <= 180:
            return 0.225
        elif days <= 360:
            return 0.20
        elif days <= 720:
            return 0.175
        else:
            return 0.15

    def _get_iof_rate(self, days: int) -> float:
        """Tabela regressiva de IOF para os primeiros 30 dias."""
        if days >= 30:
            return 0.0
        
        # Tabela simplificada de IOF (aproximada, regressiva de 96% a 3%)
        iof_table = [
            0.96, 0.93, 0.90, 0.86, 0.83, 0.80, 0.76, 0.73, 0.70, 0.66,
            0.63, 0.60, 0.56, 0.53, 0.50, 0.46, 0.43, 0.40, 0.36, 0.33,
            0.30, 0.26, 0.23, 0.20, 0.16, 0.13, 0.10, 0.06, 0.03, 0.00
        ]
        return iof_table[max(0, days - 1)] if days > 0 else 0.96

    async def get_daily_return(self) -> float:
        """Retorna o retorno diário aproximado."""
        if self.type == 'CDI':
            selic = get_selic_rate()
            taxa = selic * self.rate
        else:
            taxa = self.rate
        return (1 + taxa) ** (1 / 252) - 1

    async def get_risk_metrics(self) -> Dict[str, float]:
        hoje = datetime.now()
        dias = (self.maturity - hoje).days
        anos = max(0, dias) / 252
        return {"duration": anos, "volatilidade": 0.02}


class OptionAsset(Asset):
    def __init__(self, ticker: str, underlying_price: float, strike: float,
                 expiry: str, type: str, risk_free_rate: float = 0.10,
                 vol: float = 0.20, quantity: float = 1.0, purchase_price: float = 0.0):
        super().__init__(ticker, ticker, quantity, purchase_price)
        self.S = underlying_price
        self.K = strike
        self.T = max(0.0, (datetime.strptime(expiry, "%Y-%m-%d") - datetime.now()).days / 365.0)
        self.r = risk_free_rate
        self.sigma = vol
        self.type = type.lower()

    def _d1_d2(self):
        if self.T <= 0 or self.sigma <= 0:
            return 0.0, 0.0
        d1 = (np.log(self.S / self.K) + (self.r + 0.5 * self.sigma ** 2) * self.T) / (
            self.sigma * np.sqrt(self.T)
        )
        d2 = d1 - self.sigma * np.sqrt(self.T)
        return d1, d2

    async def get_price(self) -> float:
        if self.T <= 0:
            return max(0.0, self.S - self.K) if self.type == 'call' else max(0.0, self.K - self.S)

        d1, d2 = self._d1_d2()
        if self.type == 'call':
            price = (self.S * norm.cdf(d1)) - (self.K * np.exp(-self.r * self.T) * norm.cdf(d2))
        else:
            price = (self.K * np.exp(-self.r * self.T) * norm.cdf(-d2)) - (self.S * norm.cdf(-d1))
        return float(max(0.0, price))

    def get_greeks(self) -> Dict[str, float]:
        if self.T <= 0:
            return {}
        d1, d2 = self._d1_d2()
        delta = norm.cdf(d1) if self.type == 'call' else norm.cdf(d1) - 1
        gamma = norm.pdf(d1) / (self.S * self.sigma * np.sqrt(self.T))
        theta = -(self.S * norm.pdf(d1) * self.sigma) / (2 * np.sqrt(self.T))
        vega = self.S * norm.pdf(d1) * np.sqrt(self.T)
        return {"delta": delta, "gamma": gamma, "theta": theta, "vega": vega}

    async def get_daily_return(self) -> float:
        return 0.0

    async def get_risk_metrics(self) -> Dict[str, float]:
        return self.get_greeks()
