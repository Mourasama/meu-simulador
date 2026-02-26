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

# --- Gerenciamento de Autenticação ---
if 'logged_in' not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_email = None

if 'portfolios' not in st.session_state:
    st.session_state.portfolios = ["Principal"]

if 'current_portfolio' not in st.session_state:
    st.session_state.current_portfolio = st.session_state.portfolios[0]

if 'assets' not in st.session_state:
    st.session_state.assets = []
    st.session_state.db_ids = []

# --- Diálogos (Pop-ups) ---

@st.dialog("Login / Conta")
def auth_dialog():
    if not st.session_state.logged_in:
        tab_login, tab_register = st.tabs(["Login", "Cadastrar"])
        with tab_login:
            email_login = st.text_input("E-mail", key="dl_email_login")
            pass_login = st.text_input("Senha", type="password", key="dl_pass_login")
            if st.button("Entrar", key="dl_btn_login", kind="primary", use_container_width=True):
                try:
                    resp = requests.post(f"{BACKEND_URL}/auth/login", json={"email": email_login, "password": pass_login}, timeout=5)
                    if resp.status_code == 200:
                        st.session_state.logged_in = True
                        st.session_state.user_email = email_login
                        if 'portfolios' in st.session_state: del st.session_state['portfolios']
                        st.session_state.assets = None
                        st.rerun()
                    else:
                        st.error("E-mail ou senha incorretos.")
                except Exception:
                    st.error("Erro de conexão ao backend.")
        with tab_register:
            email_reg = st.text_input("E-mail", key="dl_email_reg")
            pass_reg = st.text_input("Senha", type="password", key="dl_pass_reg")
            if st.button("Cadastrar", key="dl_btn_register", use_container_width=True):
                try:
                    resp = requests.post(f"{BACKEND_URL}/auth/register", json={"email": email_reg, "password": pass_reg}, timeout=5)
                    if resp.status_code == 200:
                        st.success("Conta criada! Pode logar.")
                    else:
                        st.error("O E-mail já está em uso.")
                except Exception:
                    st.error("Erro de conexão ao backend.")
    else:
        st.write(f"Conectado como: **{st.session_state.user_email}**")
        if st.button("Sair da Conta", use_container_width=True):
            st.session_state.logged_in = False
            st.session_state.user_email = None
            if 'portfolios' in st.session_state: del st.session_state['portfolios']
            st.session_state.assets = None
            st.rerun()

@st.dialog("Adicionar Novo Ativo")
def add_asset_dialog():
    tipo_opcoes = {"Ação": "stock", "Cripto": "crypto", "Renda Fixa": "fixed_income"}
    asset_type = st.selectbox("Tipo de Ativo", list(tipo_opcoes.keys()))
    type_key = tipo_opcoes[asset_type]
    
    novo_ativo = None

    if type_key == "stock":
        query = st.text_input("Buscar Ticker (ex: PETR4, AAPL)", key="dl_stock_q")
        ticker = ""
        if len(query) >= 2:
            sugs = search_tickers(query)
            if sugs:
                opcoes = {f"{s['symbol']} - {s['name']}": s['symbol'] for s in sugs}
                sel = st.selectbox("Sugestões:", list(opcoes.keys()))
                ticker = opcoes[sel]
            else:
                ticker = query.upper()
        
        qty = st.number_input("Quantidade", min_value=0.01, value=1.0)
        price = st.number_input("Preço de Compra (R$)", min_value=0.0, value=0.0)
        dt = st.date_input("Data Compra", value=date.today()).strftime("%Y-%m-%d")
        
        if st.button("Adicionar", use_container_width=True, kind="primary"):
            if ticker:
                novo_ativo = {"type":"stock", "ticker":ticker, "quantity":qty, "purchase_price":price, "purchase_date":dt}

    elif type_key == "crypto":
        query = st.text_input("Buscar Cripto (ex: Bitcoin, ETH)", key="dl_crypto_q")
        ticker = ""
        if len(query) >= 2:
            sugs = search_tickers(query)
            criptos = [s for s in sugs if s.get('type') == 'CRYPTOCURRENCY']
            if criptos:
                opcoes = {f"{s['name']} ({s['symbol']})": s for s in criptos}
                sel = st.selectbox("Sugestões:", list(opcoes.keys()))
                ticker = opcoes[sel].get('id') or opcoes[sel].get('symbol')
            else:
                ticker = query.upper()
        
        qty = st.number_input("Quantidade", min_value=0.0001, value=0.1, format="%.4f")
        price = st.number_input("Preço de Compra (USD)", min_value=0.0, value=0.0)
        
        if st.button("Adicionar", use_container_width=True, kind="primary"):
            if ticker:
                if "/" not in ticker and len(ticker) < 6: ticker = f"{ticker.upper()}/USDT"
                novo_ativo = {"type":"crypto", "ticker":ticker, "quantity":qty, "purchase_price":price}

    elif type_key == "fixed_income":
        name = st.text_input("Nome do Ativo", placeholder="Tesouro Selic...")
        subtipo = st.selectbox("Subtipo", ["CDI", "PRE", "IPCA+"])
        rate = st.number_input("Taxa (ex: 1.1 = 110% CDI)", value=1.1)
        cap = st.number_input("Capital Inicial", min_value=0.0, value=1000.0)
        dt = st.date_input("Data Compra", value=date.today()).strftime("%Y-%m-%d")
        mat = st.date_input("Vencimento", value=date(2029,1,1)).strftime("%Y-%m-%d")
        
        if st.button("Adicionar", use_container_width=True, kind="primary"):
            if name:
                novo_ativo = {
                    "type": "fixed_income", "ticker": name, "quantity": 1.0, 
                    "purchase_price": cap, "purchase_date": dt,
                    "fixed_income_rate": rate, "fixed_income_maturity": mat, "fixed_income_type": subtipo
                }

    if novo_ativo:
        process_new_asset(novo_ativo)
        st.rerun()

@st.dialog("Gerenciar Carteira")
def manage_dialog():
    st.subheader(f"Ativos em '{st.session_state.current_portfolio}'")
    if not st.session_state.assets:
        st.info("Nenhum ativo para gerenciar.")
    else:
        for i, a in enumerate(st.session_state.assets):
            col1, col2 = st.columns([4, 1])
            col1.write(f"**{a.get('ticker')}** | Qtd: {a.get('quantity')}")
            if col2.button("🗑️", key=f"dl_del_{i}"):
                remove_asset_logic(i, a)
                st.rerun()
    
    st.divider()
    if st.button("Limpar Todos os Ativos", use_container_width=True):
        clear_portfolio_logic()
        st.rerun()
    if st.button("Apagar Esta Carteira", use_container_width=True, kind="secondary"):
        delete_portfolio_logic()
        st.rerun()

# --- Lógica de Persistência (Refatorada) ---

def process_new_asset(novo_ativo):
    try:
        payload = {"portfolio_name": st.session_state.current_portfolio, "user_email": st.session_state.user_email, "asset": novo_ativo}
        if not st.session_state.logged_in:
            st.session_state.assets.append(novo_ativo)
            st.session_state.db_ids.append(None)
        else:
            resp = requests.post(f"{BACKEND_URL}/db/asset", json=payload, timeout=5)
            if resp.status_code == 200:
                st.session_state.assets.append(novo_ativo)
    except Exception as e:
        st.error(f"Erro ao salvar: {e}")

def remove_asset_logic(index, asset):
    if st.session_state.logged_in:
        asset_id = asset.get("id") or (st.session_state.db_ids[index] if index < len(st.session_state.db_ids) else None)
        if asset_id:
            requests.delete(f"{BACKEND_URL}/db/asset/{asset_id}", params={"user_email": st.session_state.user_email}, timeout=3)
    st.session_state.assets.pop(index)
    if index < len(st.session_state.db_ids): st.session_state.db_ids.pop(index)

def clear_portfolio_logic():
    if st.session_state.logged_in:
        requests.delete(f"{BACKEND_URL}/db/portfolio", params={"name": st.session_state.current_portfolio, "user_email": st.session_state.user_email}, timeout=3)
    st.session_state.assets = []
    st.session_state.db_ids = []

def delete_portfolio_logic():
    clear_portfolio_logic()
    if st.session_state.current_portfolio in st.session_state.portfolios:
        st.session_state.portfolios.remove(st.session_state.current_portfolio)
    st.session_state.current_portfolio = st.session_state.portfolios[0] if st.session_state.portfolios else "Principal"
    st.session_state.assets = None

# --- Carregamento de Dados ---
if st.session_state.logged_in and ('portfolios' not in st.session_state or len(st.session_state.portfolios) <= 1):
    try:
        resp = requests.get(f"{BACKEND_URL}/db/portfolios", params={"user_email": st.session_state.user_email}, timeout=3)
        if resp.status_code == 200:
            st.session_state.portfolios = resp.json().get("portfolios", ["Principal"])
    except Exception: pass

if st.session_state.assets is None:
    if st.session_state.logged_in:
        try:
            resp = requests.get(f"{BACKEND_URL}/db/portfolio", params={"name": st.session_state.current_portfolio, "user_email": st.session_state.user_email}, timeout=3)
            if resp.status_code == 200:
                st.session_state.assets = resp.json()
                st.session_state.db_ids = [a.get('id') for a in st.session_state.assets]
        except Exception:
            st.session_state.assets = []
    else:
        st.session_state.assets = []

# --- Barra Lateral (Simplificada) ---
with st.sidebar:
    st.title("💰 Simulador")
    st.divider()
    st.markdown("""
    ### Sobre Mim
    **Enzo Moura de Souza**  
    *CPA-20 / C-PRO R*
    
    [🔗 LinkedIn](https://www.linkedin.com/in/enzo-moura-de-souza-7751512a2)
    """)
    st.divider()
    if st.session_state.logged_in:
        st.success(f"Logado: {st.session_state.user_email}")
    else:
        st.info("Modo Teste (dados não salvos)")

# --- Cabeçalho Principal (Botões e Seleção) ---
row1_col1, row1_col2 = st.columns([3, 1])

with row1_col1:
    st.title("Simulador de Carteira")
    c1, c2, c3, c4 = st.columns(4)
    if c1.button("➕ Novo Ativo", use_container_width=True):
        add_asset_dialog()
    if c2.button("⚙️ Gerenciar", use_container_width=True):
        manage_dialog()
    if c3.button("👤 Conta", use_container_width=True):
        auth_dialog()
    novo_p = st.text_input("", placeholder="Nova Carteira...", label_visibility="collapsed")
    if novo_p:
        if novo_p not in st.session_state.portfolios:
            st.session_state.portfolios.append(novo_p)
            st.session_state.current_portfolio = novo_p
            st.session_state.assets = None
            st.rerun()

with row1_col2:
    st.write("") # Espaçamento
    st.write("")
    selected_portfolio = st.selectbox(
        "Carteira Ativa", 
        st.session_state.portfolios, 
        index=st.session_state.portfolios.index(st.session_state.current_portfolio) if st.session_state.current_portfolio in st.session_state.portfolios else 0
    )
    if selected_portfolio != st.session_state.current_portfolio:
        st.session_state.current_portfolio = selected_portfolio
        st.session_state.assets = None
        st.rerun()

# Tabs
tab1, tab2, tab4 = st.tabs(["Dashboard", "Simulação de Cenários", "Comparar Carteiras"])

# ===================== TAB 1: DASHBOARD =====================
with tab1:
    st.subheader(f"Visão da Carteira: {st.session_state.current_portfolio}")
    if not st.session_state.assets:
        st.info("Utilize o botão **➕ Novo Ativo** no topo para começar a montar sua carteira.")
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
        st.info("Adicione ativos no botão **➕ Novo Ativo** para simular cenários.")
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
