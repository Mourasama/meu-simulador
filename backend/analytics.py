from typing import List, Dict, Any
import numpy as np
import pandas as pd
from backend.models import Asset, OptionAsset, StockAsset, CryptoAsset, FixedIncomeAsset

class Portfolio:
    def __init__(self):
        self.assets: List[Asset] = []

    def add_asset(self, asset: Asset):
        self.assets.append(asset)

    async def get_total_value(self) -> float:
        total = 0.0
        for asset in self.assets:
            try:
                price = await asset.get_price()
                total += asset.get_position_value(price)
            except Exception as e:
                print(f"Erro ao obter preço de {asset.name}: {e}")
        return total

    async def get_allocation(self) -> Dict[str, float]:
        allocation = {}
        total_value = await self.get_total_value()
        if total_value == 0:
            return {}

        for asset in self.assets:
            try:
                price = await asset.get_price()
                val = asset.get_position_value(price)
                allocation[asset.name] = val / total_value
            except Exception:
                pass
        return allocation

    async def get_detailed_positions(self) -> List[Dict[str, Any]]:
        """Returns per-asset details: current price, value, P&L."""
        positions = []
        for asset in self.assets:
            try:
                current_price = await asset.get_price()
                current_value = asset.get_position_value(current_price)
                purchase_value = asset.purchase_price * asset.quantity
                pnl = current_value - purchase_value
                pnl_pct = (pnl / purchase_value * 100) if purchase_value > 0 else 0.0

                positions.append({
                    "nome": asset.name,
                    "tipo": type(asset).__name__.replace("Asset", ""),
                    "quantidade": asset.quantity,
                    "preco_compra": asset.purchase_price,
                    "preco_atual": current_price,
                    "valor_atual": current_value,
                    "lucro_prejuizo": pnl,
                    "lucro_prejuizo_pct": pnl_pct,
                })
            except Exception as e:
                positions.append({
                    "nome": asset.name,
                    "tipo": type(asset).__name__.replace("Asset", ""),
                    "quantidade": asset.quantity,
                    "preco_compra": asset.purchase_price,
                    "preco_atual": 0.0,
                    "valor_atual": 0.0,
                    "lucro_prejuizo": 0.0,
                    "lucro_prejuizo_pct": 0.0,
                    "erro": str(e),
                })
        return positions


class ScenarioSimulator:
    @staticmethod
    async def simulate_scenario(portfolio: Portfolio, shock_factor: str, shock_magnitude: float) -> float:
        """
        shock_factor: 'dolar', 'juros', 'bolsa_cripto'
        shock_magnitude: percentage change (e.g. 0.10 for +10%)
        Returns: Portfolio value after shock
        """
        new_total_value = 0.0

        for asset in portfolio.assets:
            try:
                price = await asset.get_price()
            except Exception:
                price = 0.0

            if shock_factor == 'dolar':
                # Crypto e ETFs internacionais são correlacionados ao USD
                if isinstance(asset, CryptoAsset):
                    price *= (1 + shock_magnitude)
                elif isinstance(asset, StockAsset) and any(t in asset.ticker for t in ['IVVB', 'BOVA', 'SPY', 'QQQ']):
                    price *= (1 + shock_magnitude)

            elif shock_factor == 'juros':
                if isinstance(asset, FixedIncomeAsset):
                    price *= (1 + shock_magnitude)

            elif shock_factor == 'bolsa_cripto':
                if isinstance(asset, StockAsset) or isinstance(asset, CryptoAsset):
                    price *= (1 + shock_magnitude)
                elif isinstance(asset, OptionAsset):
                    # Opções de venda (put) se valorizam inversamente; calls acompanham
                    if asset.type == 'put':
                        price *= (1 - shock_magnitude)
                    else:
                        price *= max(0, 1 + shock_magnitude)

            new_total_value += asset.get_position_value(price)

        return new_total_value


class StrategyAnalytics:
    # Descrições amigáveis de cada estratégia
    DESCRIPTIONS = {
        "trava_de_alta": (
            "**Trava de Alta (Bull Call Spread):** Compra uma Call com strike mais baixo (K1) e vende "
            "uma Call com strike mais alto (K2). Ideal quando você acredita em alta moderada do ativo. "
            "O ganho máximo é limitado, mas o custo (débito líquido) também é reduzido."
        ),
        "condor_de_ferro": (
            "**Condor de Ferro (Iron Condor):** Combina uma trava de baixa com puts e uma trava de alta "
            "com calls. Lucra quando o ativo fica dentro de um intervalo de preços até o vencimento. "
            "Estratégia de renda, ideal para mercados lateralizados."
        ),
        "venda_coberta": (
            "**Venda Coberta (Covered Call):** Você possui a ação e vende uma Call sobre ela. "
            "Gera renda com o prêmio recebido e protege parcialmente contra quedas. "
            "O lucro é limitado ao strike da call vendida."
        ),
    }

    @staticmethod
    def get_payoff(strategy_type: str, spots: np.ndarray, params: Dict[str, float]) -> np.ndarray:
        """
        Calcula o payoff no vencimento para uma estratégia.
        spots: Array de preços do ativo no vencimento
        params: Parâmetros da estratégia (strikes, prêmios)
        """
        payoff = np.zeros_like(spots)

        if strategy_type == "trava_de_alta":
            k1, k2 = params['k1'], params['k2']
            p1, p2 = params['cost_k1'], params['credit_k2']
            net_debit = p1 - p2
            call1 = np.maximum(spots - k1, 0)
            call2 = np.maximum(spots - k2, 0)
            payoff = call1 - call2 - net_debit

        elif strategy_type == "condor_de_ferro":
            k1, k2, k3, k4 = params['k1'], params['k2'], params['k3'], params['k4']
            net_credit = params['net_credit']
            put1 = np.maximum(k1 - spots, 0)
            put2 = np.maximum(k2 - spots, 0)
            call3 = np.maximum(spots - k3, 0)
            call4 = np.maximum(spots - k4, 0)
            payoff = (put1 - put2) + (call4 - call3) + net_credit

        elif strategy_type == "venda_coberta":
            k = params['k']
            s0 = params['s0']
            premium = params['premium']
            stock_pnl = spots - s0
            short_call_pnl = -np.maximum(spots - k, 0)
            payoff = stock_pnl + short_call_pnl + premium

        return payoff
