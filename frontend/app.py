import streamlit as st
import requests
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, timedelta

# --- Config ---
try:
    BACKEND_URL = st.secrets["BACKEND_URL"]
except Exception:
    BACKEND_URL = "http://localhost:8000"
st.set_page_config(page_title="Simulador de Carteira", layout="wide")

# --- Premium CSS ---
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Outfit', sans-serif;
    }
    
    .stMetric {
        background: rgba(255, 255, 255, 0.05);
        border-radius: 12px;
        padding: 20px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
        transition: transform 0.3s ease;
    }
    
    .stMetric:hover {
        transform: translateY(-5px);
        border-color: #2196F3;
    }
    
    .main .block-container {
        padding-top: 2rem;
    }
    
    h1, h2, h3 {
        font-weight: 700 !important;
        letter-spacing: -0.5px;
    }
    
    .stTabs [data-baseweb="tab-list"] {
        gap: 24px;
    }
    
    .stTabs [data-baseweb="tab"] {
        height: 50px;
        white-space: pre-wrap;
        background-color: transparent;
        border-radius: 4px 4px 0px 0px;
        gap: 1px;
        padding-top: 10px;
        padding-bottom: 10px;
    }

    /* Cores vibrantes para botões primários */
    .stButton>button[kind="primary"] {
        background-color: #2196F3;
        color: white;
        border-radius: 8px;
        border: none;
        padding: 0.5rem 2rem;
        font-weight: 600;
        transition: all 0.3s ease;
    }
    
    .stButton>button[kind="primary"]:hover {
        background-color: #1976D2;
        box-shadow: 0 4px 12px rgba(33, 150, 243, 0.3);
    }
</style>
""", unsafe_allow_html=True)

# --- Helpers ---
def fmt_brl(value: float) -> str:
    """Formata valor no padrão brasileiro: R$ 1.234,56"""
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")

def fmt_pct(value: float) -> str:
    return f"{value:+.2f}%".replace(".", ",")

def tipo_label(tipo: str) -> str:
    mapa = {
        "stock": "Ação",
        "crypto": "Cripto",
        "fixed_income": "Renda Fixa",
    }
    return mapa.get(tipo, tipo)

def search_tickers(query: str):
    """Chama o endpoint de busca de tickers no backend."""
    try:
        resp = requests.get(f"{BACKEND_URL}/tickers/search", params={"q": query}, timeout=5)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return []

# --- Gerenciamento de Autenticação e Carteiras ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_email = None

st.sidebar.title("Login / Conta")
if not st.session_state.logged_in:
    tab_login, tab_register = st.sidebar.tabs(["Login", "Cadastrar"])
    with tab_login:
        email_login = st.text_input("E-mail", key="email_login")
        pass_login = st.text_input("Senha", type="password", key="pass_login")
        if st.button("Entrar", key="btn_login"):
            try:
                resp = requests.post(f"{BACKEND_URL}/auth/login", json={"email": email_login, "password": pass_login}, timeout=5)
                if resp.status_code == 200:
                    st.session_state.logged_in = True
                    st.session_state.user_email = email_login
                    # Limpa estados para forçar recarregamento do DB
                    if 'portfolios' in st.session_state: del st.session_state['portfolios']
                    st.session_state.current_portfolio = "Principal"
                    st.session_state.assets = None
                    st.rerun()
                else:
                    st.sidebar.error("E-mail ou senha incorretos.")
            except Exception:
                st.sidebar.error("Erro de conexão ao backend.")
    with tab_register:
        email_reg = st.text_input("E-mail", key="email_reg")
        pass_reg = st.text_input("Senha", type="password", key="pass_reg")
        if st.button("Cadastrar", key="btn_register"):
            try:
                resp = requests.post(f"{BACKEND_URL}/auth/register", json={"email": email_reg, "password": pass_reg}, timeout=5)
                if resp.status_code == 200:
                    st.sidebar.success("Conta criada! Pode logar.")
                else:
                    st.sidebar.error("O E-mail já está em uso ou é inválido.")
            except Exception:
                st.sidebar.error("Erro de conexão ao backend.")
    st.sidebar.info("Modo Teste: os dados não são salvos sem login.")
    st.sidebar.divider()
else:
    st.sidebar.success(f"Logado: {st.session_state.user_email}")
    if st.sidebar.button("Sair"):
        st.session_state.logged_in = False
        st.session_state.user_email = None
        if 'portfolios' in st.session_state: del st.session_state['portfolios']
        st.session_state.current_portfolio = "Principal"
        st.session_state.assets = None
        st.rerun()
    st.sidebar.divider()

if 'portfolios' not in st.session_state:
    if st.session_state.logged_in:
        try:
            resp = requests.get(f"{BACKEND_URL}/db/portfolios", params={"user_email": st.session_state.user_email}, timeout=3)
            if resp.status_code == 200:
                st.session_state.portfolios = resp.json().get("portfolios", ["Principal"])
            else:
                st.session_state.portfolios = ["Principal"]
        except Exception:
            st.session_state.portfolios = ["Principal"]
    else:
        st.session_state.portfolios = ["Principal"]

if 'current_portfolio' not in st.session_state:
    st.session_state.current_portfolio = st.session_state.portfolios[0]

# Sidebar: Seleção de Carteira
st.sidebar.title("Carteiras")
novo_nome_carteira = st.sidebar.text_input("Criar nova carteira", placeholder="Nome da nova carteira...")
if st.sidebar.button("Criar") and novo_nome_carteira:
    if novo_nome_carteira not in st.session_state.portfolios:
        st.session_state.portfolios.append(novo_nome_carteira)
        st.session_state.current_portfolio = novo_nome_carteira
        # Forçar recarregamento para a nova carteira
        st.session_state.assets = None
        st.rerun()

selected_portfolio = st.sidebar.selectbox(
    "Carteira Ativa", 
    st.session_state.portfolios, 
    index=st.session_state.portfolios.index(st.session_state.current_portfolio) if st.session_state.current_portfolio in st.session_state.portfolios else 0
)

# Se a carteira mudou, recarregar os ativos
if selected_portfolio != st.session_state.current_portfolio or 'assets' not in st.session_state or st.session_state.assets is None:
    st.session_state.current_portfolio = selected_portfolio
    if st.session_state.logged_in:
        try:
            resp = requests.get(f"{BACKEND_URL}/db/portfolio", params={"name": selected_portfolio, "user_email": st.session_state.user_email}, timeout=3)
            if resp.status_code == 200:
                st.session_state.assets = resp.json()
                st.session_state.db_ids = [a.get('id') for a in st.session_state.assets]
            else:
                st.session_state.assets = []
                st.session_state.db_ids = []
        except Exception:
            st.session_state.assets = []
            st.session_state.db_ids = []
    else:
        st.session_state.assets = []
        st.session_state.db_ids = []

st.sidebar.divider()

# --- Sidebar: Adicionar Ativo ---
st.sidebar.header(f"Adicionar Ativo em '{st.session_state.current_portfolio}'")
tipo_opcoes = {
    "Ação": "stock",
    "Cripto": "crypto",
    "Renda Fixa": "fixed_income",
}
tipo_label_sel = st.sidebar.selectbox("Tipo de Ativo", list(tipo_opcoes.keys()))
asset_type = tipo_opcoes[tipo_label_sel]

novo_ativo = None

# ── AÇÃO ──────────────────────────────────────────────────────────────────────
if asset_type == "stock":
    st.sidebar.markdown("**Buscar Ação / ETF**")
    ticker_query = st.sidebar.text_input(
        "Digite o ticker ou nome",
        key="stock_query",
        placeholder="ex: PETR4, Vale, AAPL..."
    )

    ticker_selecionado = ""
    if ticker_query and len(ticker_query) >= 2:
        with st.sidebar:
            with st.spinner("Buscando..."):
                sugestoes = search_tickers(ticker_query)
        
        if sugestoes:
            # Filtrar por EQUITY ou mostrar tudo se for busca genérica
            opcoes = {f"{s['symbol']} — {s['name']} ({s.get('exchange', 'Stock')})": s['symbol'] for s in sugestoes}
            escolha = st.sidebar.selectbox("Resultados encontrados:", list(opcoes.keys()), key="stock_sel")
            ticker_selecionado = opcoes[escolha]
            st.sidebar.caption(f"Ticker selecionado: **{ticker_selecionado}**")
        else:
            ticker_selecionado = ticker_query.upper()

    qty = st.sidebar.number_input("Quantidade", min_value=0.01, value=1.0, step=1.0, key="stock_qty")
    purchase_price = st.sidebar.number_input(
        "Preço de Compra (R$)",
        min_value=0.0, value=0.0, step=0.01, key="stock_pp",
    )
    purchase_date_stock = st.sidebar.date_input(
        "Data de Compra", value=date.today(), key="stock_date"
    ).strftime("%Y-%m-%d")

    if st.sidebar.button("Adicionar Ação", key="btn_stock"):
        if not ticker_selecionado:
            st.sidebar.error("Selecione um ticker válido.")
        else:
            novo_ativo = {
                "type": "stock",
                "ticker": ticker_selecionado,
                "quantity": qty,
                "purchase_price": purchase_price,
                "purchase_date": purchase_date_stock,
            }

# ── CRIPTO ────────────────────────────────────────────────────────────────────
elif asset_type == "crypto":
    st.sidebar.markdown("**Buscar Cripto**")
    crypto_query = st.sidebar.text_input(
        "Digite o nome ou símbolo",
        key="crypto_query",
        placeholder="ex: Bitcoin, Ethereum, SOL..."
    )

    selected_crypto_id = ""
    crypto_ticker = ""
    
    if crypto_query and len(crypto_query) >= 2:
        with st.sidebar:
            with st.spinner("Buscando..."):
                sugestoes = search_tickers(crypto_query)
        
        # Filtrar sugestões do CoinGecko ou que sejam CRYPTOCURRENCY
        cripto_sugestoes = [s for s in sugestoes if s.get('type') == 'CRYPTOCURRENCY']
        
        if cripto_sugestoes:
            # Mostra o Nome e Símbolo
            opcoes = {f"{s['name']} ({s['symbol']})": s for s in cripto_sugestoes}
            escolha_label = st.sidebar.selectbox("Selecione a cripto:", list(opcoes.keys()), key="crypto_sel")
            selected_data = opcoes[escolha_label]
            
            # Priorizamos o Símbolo para o ticker principal (melhor para fallbacks)
            # Mas guardamos o ID se disponível para o CoinGecko search no backend.
            crypto_ticker = selected_data.get('symbol', '').upper()
            selected_crypto_id = selected_data.get('id', '').lower()
            
            # Formatação visual
            st.sidebar.caption(f"Selecionado: **{selected_data['name']}**")
        else:
            crypto_ticker = crypto_query.upper()

    qty = st.sidebar.number_input("Quantidade", min_value=0.0001, value=0.01, step=0.001, format="%.4f", key="crypto_qty")
    purchase_price = st.sidebar.number_input(
        "Preço de Compra (USD)", min_value=0.0, value=0.0, step=0.01, key="crypto_pp"
    )

    if st.sidebar.button("Adicionar Cripto", key="btn_crypto"):
        final_ticker = selected_crypto_id if selected_crypto_id else crypto_ticker
        if not final_ticker:
            st.sidebar.error("Informe uma cripto válida.")
        else:
            # Se for par manual sem ID, garantir formato /USDT
            if "/" not in final_ticker and not selected_crypto_id:
                 final_ticker = f"{final_ticker}/USDT"

            novo_ativo = {
                "type": "crypto",
                "ticker": final_ticker,
                "quantity": qty,
                "purchase_price": purchase_price,
            }

# ── RENDA FIXA ────────────────────────────────────────────────────────────────
elif asset_type == "fixed_income":
    st.sidebar.markdown("**Renda Fixa**")
    st.sidebar.caption(
        "O Valor Atual é calculado automaticamente: "
        "**Capital Inicial × (1 + taxa)^(dias corridos)**"
    )
    name = st.sidebar.text_input("Nome (ex: Tesouro Selic 2029)", key="fi_name")
    fi_type = st.sidebar.selectbox("Subtipo", ["CDI", "PRE", "IPCA+"], key="fi_type")

    if fi_type == "CDI":
        rate = st.sidebar.number_input(
            "% do CDI (ex: 1.10 = 110% CDI)", value=1.10, step=0.01, format="%.2f", key="fi_rate",
            help="Percentual do CDI contratado. 1.0 = 100% CDI, 1.10 = 110% CDI."
        )
    elif fi_type == "PRE":
        rate = st.sidebar.number_input(
            "Taxa Pré-fixada (ex: 0.12 = 12% a.a.)", value=0.12, step=0.005, format="%.4f", key="fi_rate",
            help="Taxa anual pré-fixada como decimal."
        )
    else:  # IPCA+
        rate = st.sidebar.number_input(
            "Spread Real sobre IPCA (ex: 0.06 = IPCA + 6%)", value=0.06, step=0.005, format="%.4f", key="fi_rate",
            help="Spread real acima do IPCA como decimal."
        )

    maturity = st.sidebar.date_input(
        "Data de Vencimento", value=date(2029, 3, 1), key="fi_maturity"
    ).strftime("%Y-%m-%d")

    capital_inicial = st.sidebar.number_input(
        "Capital Inicial (R$)",
        min_value=0.01, value=1000.0, step=100.0, key="fi_capital",
        help="Valor total investido. O sistema calcula os juros acumulados desde a data de compra.",
    )
    purchase_date_fi = st.sidebar.date_input(
        "Data de Compra (para cálculo pro-rata)",
        value=date.today() - timedelta(days=365),
        key="fi_date",
    ).strftime("%Y-%m-%d")

    if st.sidebar.button("Adicionar Renda Fixa", key="btn_fi"):
        if not name:
            st.sidebar.error("Informe um nome para o ativo.")
        else:
            novo_ativo = {
                "type": "fixed_income",
                "ticker": name,
                "quantity": 1.0,           # RF usa capital_inicial como valor total
                "purchase_price": capital_inicial,  # capital_inicial = purchase_price × qty(1)
                "purchase_date": purchase_date_fi,
                "fixed_income_rate": rate,
                "fixed_income_maturity": maturity,
                "fixed_income_type": fi_type,
            }

# Processar novo ativo
if novo_ativo:
    try:
        payload = {
            "portfolio_name": st.session_state.current_portfolio,
            "user_email": st.session_state.user_email,
            "asset": novo_ativo
        }
        # Se não logado, apenas adicionamos ao session state para teste
        if not st.session_state.logged_in:
            st.session_state.assets.append(novo_ativo)
            st.session_state.db_ids.append(None)
            st.success("Ativo adicionado (Modo Teste - Não será salvo)")
            st.rerun()
        else:
            save_resp = requests.post(f"{BACKEND_URL}/db/asset", json=payload, timeout=5)
            if save_resp.status_code == 200:
                saved_id = save_resp.json().get("id")
                novo_ativo["id"] = saved_id
                st.session_state.assets.append(novo_ativo)
                st.session_state.db_ids.append(saved_id)
                st.success("Ativo adicionado e salvo!")
                st.rerun()
            else:
                st.sidebar.error(f"Erro ao salvar ativo: {save_resp.text}")
    except Exception as e:
        st.sidebar.error(f"Erro de conexão: {e}")

# --- Carteira Atual na Sidebar ---
st.sidebar.divider()
st.sidebar.subheader("Carteira Atual")
if st.session_state.assets:
    for i, a in enumerate(st.session_state.assets):
        col_a, col_b = st.sidebar.columns([3, 1])
        col_a.write(f"**{a.get('ticker', '?')}** ({tipo_label(a.get('type', ''))})")
        col_a.caption(f"Qtd: {a.get('quantity', 0)} | Compra: {fmt_brl(a.get('purchase_price', 0))}")
        if col_b.button("🗑️", key=f"del_{i}"):
            if st.session_state.logged_in:
                asset_id = a.get("id") or (st.session_state.db_ids[i] if i < len(st.session_state.db_ids) else None)
                if asset_id:
                    requests.delete(f"{BACKEND_URL}/db/asset/{asset_id}", params={"user_email": st.session_state.user_email}, timeout=3)
            st.session_state.assets.pop(i)
            if i < len(st.session_state.db_ids):
                st.session_state.db_ids.pop(i)
            st.rerun()

    col_btn1, col_btn2 = st.sidebar.columns(2)
    if col_btn1.button("Limpar Ativos"):
        if st.session_state.logged_in:
            requests.delete(f"{BACKEND_URL}/db/portfolio", params={"name": st.session_state.current_portfolio, "user_email": st.session_state.user_email}, timeout=3)
        st.session_state.assets = []
        st.session_state.db_ids = []
        st.rerun()
    if col_btn2.button("Apagar Carteira"):
        if st.session_state.logged_in:
            requests.delete(f"{BACKEND_URL}/db/portfolio", params={"name": st.session_state.current_portfolio, "user_email": st.session_state.user_email}, timeout=3)
        if st.session_state.current_portfolio in st.session_state.portfolios:
            st.session_state.portfolios.remove(st.session_state.current_portfolio)
        st.session_state.current_portfolio = st.session_state.portfolios[0] if st.session_state.portfolios else "Principal"
        st.session_state.assets = None
        st.rerun()
else:
    st.sidebar.info("Nenhum ativo na carteira.")

# --- Título Principal e Sobre Mim ---
col_head1, col_head2 = st.columns([2, 1])

with col_head1:
    st.title("Simulador de Carteira Financeira")

with col_head2:
    st.markdown("""
    <div style="background: rgba(255, 255, 255, 0.05); padding: 15px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.1);">
        <h4 style="margin-top: 0; color: #2196F3;">Sobre Mim</h4>
        <p style="font-size: 0.9rem; margin-bottom: 8px;">
            Sou <b>Enzo Moura de Souza</b>, Profissional certificado <b>CPA-20/C-PRO R</b>.
        </p>
        <p style="font-size: 0.85rem; color: #ccc; margin-bottom: 12px;">
            Desenvolvi este site para estudar programação e ajudar profissionais de mercado a testarem suas ideias.
        </p>
        <a href="https://www.linkedin.com/in/enzo-moura-de-souza-7751512a2" target="_blank" style="color: #2196F3; text-decoration: none; font-weight: 600;">
            🔗 Meu LinkedIn
        </a>
    </div>
    """, unsafe_allow_html=True)

# Tabs
tab1, tab2, tab4 = st.tabs(["Dashboard", "Simulação de Cenários", "Comparar Carteiras"])

# ===================== TAB 1: DASHBOARD =====================
with tab1:
    st.subheader(f"Visão da Carteira: {st.session_state.current_portfolio}")
    if not st.session_state.assets:
        st.info("Adicione ativos na barra lateral para visualizar o dashboard.")
    else:
        with st.spinner("Calculando carteira com preços ao vivo..."):
            try:
                payload = {"assets": st.session_state.assets}
                response = requests.post(f"{BACKEND_URL}/portfolio/calculate", json=payload, timeout=60)

                if response.status_code == 200:
                    data = response.json()
                    total_val = data.get("total_value", 0)
                    allocation = data.get("allocation", {})
                    positions = data.get("positions", [])

                    # --- Métricas de Topo ---
                    # Valor investido: para RF é purchase_price (capital inicial), para outros é purchase_price × qty
                    total_compra = 0.0
                    for a in st.session_state.assets:
                        pp = a.get("purchase_price", 0) or 0
                        qty = a.get("quantity", 0) or 0
                        if a.get("type") == "fixed_income":
                            total_compra += pp  # purchase_price já é o capital total (qty=1)
                        else:
                            total_compra += pp * qty

                    total_pnl = total_val - total_compra
                    total_pnl_pct = (total_pnl / total_compra * 100) if total_compra > 0 else 0

                    col1, col2, col3 = st.columns(3)
                    col1.metric(
                        "Valor Total da Carteira",
                        fmt_brl(total_val),
                        fmt_pct(total_pnl_pct) if total_compra > 0 else None,
                    )
                    col2.metric("Capital Investido", fmt_brl(total_compra))
                    pnl_label = "Lucro Total" if total_pnl >= 0 else "Prejuízo Total"
                    col3.metric(pnl_label, fmt_brl(total_pnl))

                    st.divider()

                    # --- Tabela de Posições ---
                    if positions:
                        st.subheader("Posições Detalhadas")
                        df_pos = pd.DataFrame(positions)

                        df_display = pd.DataFrame({
                            "Ativo": df_pos["nome"],
                            "Tipo": df_pos["tipo"],
                            "Qtd": df_pos["quantidade"],
                            "Preço Compra": df_pos["preco_compra"].apply(fmt_brl),
                            "Preço Atual": df_pos["preco_atual"].apply(fmt_brl),
                            "Valor Atual": df_pos["valor_atual"].apply(fmt_brl),
                            "L/P (R$)": df_pos["lucro_prejuizo"].apply(fmt_brl),
                            "L/P (%)": df_pos["lucro_prejuizo_pct"].apply(fmt_pct),
                        })
                        st.dataframe(df_display, use_container_width=True, hide_index=True)

                    # --- Gráfico de Alocação por Market Value ---
                    if allocation:
                        st.subheader("Alocação Real da Carteira (por Market Value)")
                        st.caption(
                            "Proporção calculada com base no **Valor de Mercado atual** "
                            "(Quantidade × Preço Atual) de cada ativo."
                        )

                        # Agrupar por classe de ativo para visão macro
                        col_pie1, col_pie2 = st.columns(2)

                        with col_pie1:
                            # Pizza por ativo individual
                            fig_pie = px.pie(
                                names=list(allocation.keys()),
                                values=list(allocation.values()),
                                title="Por Ativo",
                                hole=0.4,
                            )
                            fig_pie.update_traces(textinfo="percent+label")
                            st.plotly_chart(fig_pie, use_container_width=True)

                        with col_pie2:
                            # Pizza por classe de ativo
                            if positions:
                                tipo_map = {"Stock": "Ação", "Crypto": "Cripto",
                                            "FixedIncome": "Renda Fixa"}
                                classe_vals: dict = {}
                                for p in positions:
                                    classe = tipo_map.get(p["tipo"], p["tipo"])
                                    classe_vals[classe] = classe_vals.get(classe, 0) + p["valor_atual"]

                                fig_classe = px.pie(
                                    names=list(classe_vals.keys()),
                                    values=list(classe_vals.values()),
                                    title="Por Classe de Ativo",
                                    hole=0.4,
                                    color_discrete_map={
                                        "Ação": "#2196F3",
                                        "Cripto": "#FF9800",
                                        "Renda Fixa": "#4CAF50",
                                    },
                                )
                                fig_classe.update_traces(textinfo="percent+label")
                                st.plotly_chart(fig_classe, use_container_width=True)

                else:
                    st.error(f"Erro ao calcular carteira: {response.text}")

            except requests.exceptions.ConnectionError:
                st.error("Não foi possível conectar ao backend. Certifique-se de que o servidor está rodando.")
            except Exception as e:
                st.error(f"Erro inesperado: {e}")

# ===================== TAB 2: SIMULAÇÃO =====================
with tab2:
    st.header("Simulação de Cenários de Mercado")

    if not st.session_state.assets:
        st.info("Adicione ativos na barra lateral para simular cenários.")
    else:
        cenario_opcoes = {
            "Resultado Bolsa / Cripto": "bolsa_cripto",
            "Resultado Dólar": "dolar",
            "Resultado Renda Fixa (Juros)": "juros",
        }

        col1, col2 = st.columns(2)
        with col1:
            cenario_label = st.selectbox("Cenário de Choque", list(cenario_opcoes.keys()))
            cenario = cenario_opcoes[cenario_label]

        with col2:
            if cenario == "bolsa_cripto":
                st.info(
                    "**Resultado Bolsa / Cripto:** Aplica a variação percentual escolhida diretamente no preço das Ações e Criptomoedas da carteira."
                )
            elif cenario == "dolar":
                st.info(
                    "**Resultado Dólar:** Aplica a variação percentual no preço de Criptomoedas e ETFs internacionais pareados ao Dólar."
                )
            elif cenario == "juros":
                st.info(
                    "**Resultado Renda Fixa (Juros):** Aplica a variação percentual no valor de mercado dos títulos de Renda Fixa."
                )
            
            magnitude = st.number_input(
                "Variação Percentual Desejada (ex: 0.10 = +10%, -0.20 = -20%)",
                value=0.00, step=0.01, format="%.2f"
            )

        if st.button("Executar Simulação", type="primary"):
            with st.spinner("Simulando..."):
                try:
                    payload = {
                        "assets": st.session_state.assets,
                        "shock_factor": cenario,
                        "shock_magnitude": magnitude,
                    }
                    response = requests.post(f"{BACKEND_URL}/portfolio/simulate", json=payload, timeout=60)

                    if response.status_code == 200:
                        sim_val = response.json()["simulated_value"]

                        base_res = requests.post(
                            f"{BACKEND_URL}/portfolio/calculate",
                            json={"assets": st.session_state.assets},
                            timeout=60,
                        )
                        base_val = base_res.json()["total_value"] if base_res.status_code == 200 else 0

                        delta = sim_val - base_val
                        pct = (delta / base_val * 100) if base_val else 0

                        c1, c2, c3 = st.columns(3)
                        c1.metric("Valor Original", fmt_brl(base_val))
                        c2.metric("Valor Simulado", fmt_brl(sim_val), fmt_pct(pct))
                        c3.metric("Impacto", fmt_brl(delta))

                        df_sim = pd.DataFrame({
                            "Cenário": ["Atual", "Simulado"],
                            "Valor (R$)": [base_val, sim_val],
                            "Cor": ["#2196F3", "#F44336" if delta < 0 else "#4CAF50"],
                        })
                        fig_bar = go.Figure(go.Bar(
                            x=df_sim["Cenário"],
                            y=df_sim["Valor (R$)"],
                            marker_color=df_sim["Cor"],
                            text=[fmt_brl(v) for v in df_sim["Valor (R$)"]],
                            textposition="outside",
                        ))
                        fig_bar.update_layout(
                            title=f"Impacto do Cenário: {cenario_label}",
                            yaxis_title="Valor da Carteira (R$)",
                            showlegend=False,
                        )
                        st.plotly_chart(fig_bar, use_container_width=True)

                    else:
                        st.error(f"Erro na simulação: {response.text}")

                except Exception as e:
                    st.error(f"Falha na simulação: {e}")

# ===================== TAB 4: COMPARAR CARTEIRAS =====================
with tab4:
    st.header("Comparação Simultânea de Carteiras")
    st.caption("Selecione quais carteiras você deseja comparar.")

    todas_carteiras = st.session_state.portfolios
    
    carteiras_para_comparar = st.multiselect(
        "Selecione as carteiras",
        todas_carteiras,
        default=todas_carteiras if len(todas_carteiras) <= 3 else todas_carteiras[:3]
    )

    if not carteiras_para_comparar:
        st.warning("Selecione pelo menos uma carteira para continuar.")
    else:
        if st.button("Atualizar Comparação", type="primary"):
            with st.spinner("Buscando dados das carteiras..."):
                comparativo = []
                alocacoes = []

                for cart_name in carteiras_para_comparar:
                    # 1. Obter os ativos da carteira no DB
                    try:
                        resp_db = requests.get(f"{BACKEND_URL}/db/portfolio", params={"name": cart_name}, timeout=5)
                        if resp_db.status_code == 200:
                            cart_assets = resp_db.json()
                            
                            if not cart_assets:
                                comparativo.append({
                                    "Carteira": cart_name,
                                    "Valor Total": 0.0,
                                    "Capital Investido": 0.0,
                                    "Lucro/Prejuízo": 0.0,
                                    "Rentabilidade": 0.0
                                })
                                continue
                            
                            # 2. Calcular carteira
                            resp_calc = requests.post(
                                f"{BACKEND_URL}/portfolio/calculate", 
                                json={"assets": cart_assets}, 
                                timeout=30
                            )
                            
                            if resp_calc.status_code == 200:
                                data = resp_calc.json()
                                total_val = data.get("total_value", 0)
                                positions = data.get("positions", [])
                                allocation = data.get("allocation", {})
                                
                                # Calcular capital investido
                                total_compra = 0.0
                                for a in cart_assets:
                                    pp = a.get("purchase_price", 0) or 0
                                    qty = a.get("quantity", 0) or 0
                                    if a.get("type") == "fixed_income":
                                        total_compra += pp
                                    else:
                                        total_compra += pp * qty
                                        
                                total_pnl = total_val - total_compra
                                rentabilidade = (total_pnl / total_compra * 100) if total_compra > 0 else 0
                                
                                comparativo.append({
                                    "Carteira": cart_name,
                                    "Valor Total": total_val,
                                    "Capital Investido": total_compra,
                                    "Lucro/Prejuízo": total_pnl,
                                    "Rentabilidade (%)": rentabilidade
                                })
                                
                                # Processar alocações por classe
                                tipo_map = {"Stock": "Ação", "Crypto": "Cripto",
                                            "FixedIncome": "Renda Fixa", "Option": "Opção"}
                                classe_vals: dict = {}
                                for p in positions:
                                    classe = tipo_map.get(p["tipo"], p["tipo"])
                                    classe_vals[classe] = classe_vals.get(classe, 0) + p["valor_atual"]
                                    
                                for classe, valor in classe_vals.items():
                                    alocacoes.append({
                                        "Carteira": cart_name,
                                        "Classe": classe,
                                        "Valor": valor
                                    })
                            else:
                                st.error(f"Erro ao calcular a carteira {cart_name}.")
                        else:
                             st.error(f"Erro ao buscar a carteira {cart_name} do banco de dados.")
                    except Exception as e:
                        st.error(f"Erro de conexão na carteira {cart_name}: {e}")
                
                # Exibir as tabelas e gráficos apenas se tivemos sucesso em processar os dados
                if comparativo:
                    # 1. Tabela de Resumo Financeiro
                    df_comp = pd.DataFrame(comparativo)
                    
                    st.subheader("Resumo Financeiro")
                    
                    # Criar colunas baseadas na quantidade de carteiras selecionadas (max 4 na mesma linha)
                    cols = st.columns(min(len(df_comp), 4))
                    for i, row in df_comp.iterrows():
                        with cols[i % len(cols)]:
                            st.write(f"### {row['Carteira']}")
                            st.metric("Total", fmt_brl(row['Valor Total']), fmt_pct(row['Rentabilidade (%)']))
                            st.caption(f"Investido: {fmt_brl(row['Capital Investido'])}")
                            
                    st.divider()

                    # 2. Gráfico de Comparativo de Patrimônio
                    st.subheader("Comparativo de Patrimônio")
                    
                    df_melted = df_comp.melt(id_vars=["Carteira"], value_vars=["Valor Total", "Capital Investido"], 
                                           var_name="Métrica", value_name="Valor (R$)")
                    
                    fig_bars = px.bar(df_melted, x="Carteira", y="Valor (R$)", color="Métrica", barmode="group",
                                     title="Valor Total vs Capital Investido",
                                     color_discrete_map={"Valor Total": "#2196F3", "Capital Investido": "#9E9E9E"})
                    st.plotly_chart(fig_bars, use_container_width=True)
                    
                    # 3. Gráfico de Alocação
                    if alocacoes:
                        st.divider()
                        st.subheader("Alocação por Classe de Ativo")
                        df_aloc = pd.DataFrame(alocacoes)
                        
                        fig_aloc = px.bar(df_aloc, x="Carteira", y="Valor", color="Classe", barmode="stack",
                                         title="Composição das Carteiras",
                                         color_discrete_map={
                                            "Ação": "#2196F3",
                                            "Cripto": "#FF9800",
                                            "Renda Fixa": "#4CAF50",
                                            "Opção": "#9C27B0",
                                         })
                        st.plotly_chart(fig_aloc, use_container_width=True)
