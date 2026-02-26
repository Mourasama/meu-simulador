import sqlite3
import json
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime
import os

# Store DB next to this file so it persists across runs
DB_PATH = os.path.join(os.path.dirname(__file__), "..", "portfolio.db")

def _get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()

def init_db():
    conn = _get_conn()
    cursor = conn.cursor()
    
    # Criar tabela de usuários
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_name TEXT DEFAULT 'Principal',
            user_email TEXT DEFAULT NULL,
            ticker TEXT NOT NULL,
            type TEXT NOT NULL,
            quantity REAL NOT NULL,
            purchase_price REAL DEFAULT 0.0,
            purchase_date TEXT,
            extra_params TEXT
        )
    ''')
    # Check if we need to migrate existing DB to add columns
    cursor.execute("PRAGMA table_info(portfolio)")
    columns = [col['name'] for col in cursor.fetchall()]
    if 'portfolio_name' not in columns:
        cursor.execute("ALTER TABLE portfolio ADD COLUMN portfolio_name TEXT DEFAULT 'Principal'")
    if 'user_email' not in columns:
        cursor.execute("ALTER TABLE portfolio ADD COLUMN user_email TEXT DEFAULT NULL")
    conn.commit()
    conn.close()

def create_user(email: str, password: str) -> bool:
    conn = _get_conn()
    cursor = conn.cursor()
    try:
        pw_hash = hash_password(password)
        cursor.execute('INSERT INTO users (email, password_hash) VALUES (?, ?)', (email, pw_hash))
        conn.commit()
        res = True
    except sqlite3.IntegrityError:
        res = False
    except Exception:
        res = False
    finally:
        conn.close()
    return res

def verify_user(email: str, password: str) -> bool:
    conn = _get_conn()
    cursor = conn.cursor()
    pw_hash = hash_password(password)
    cursor.execute('SELECT 1 FROM users WHERE email = ? AND password_hash = ?', (email, pw_hash))
    user = cursor.fetchone()
    conn.close()
    return user is not None

def add_asset(asset_data: Dict[str, Any], user_email: Optional[str] = None):
    conn = _get_conn()
    cursor = conn.cursor()

    portfolio_name = asset_data.get('portfolio_name', 'Principal')
    ticker = asset_data.get('ticker')
    asset_type = asset_data.get('type')
    quantity = asset_data.get('quantity')
    purchase_price = asset_data.get('purchase_price', 0.0)
    purchase_date = asset_data.get('purchase_date', datetime.now().strftime("%Y-%m-%d"))

    extra_params = {k: v for k, v in asset_data.items() if k not in
                    ['portfolio_name', 'ticker', 'type', 'quantity', 'purchase_price', 'purchase_date', 'user_email']}

    cursor.execute('''
        INSERT INTO portfolio (portfolio_name, ticker, type, quantity, purchase_price, purchase_date, user_email, extra_params)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ''', (portfolio_name, ticker, asset_type, quantity, purchase_price, purchase_date, user_email, json.dumps(extra_params)))

    conn.commit()
    last_id = cursor.lastrowid
    conn.close()
    return last_id

def get_portfolios(user_email: Optional[str] = None) -> List[str]:
    conn = _get_conn()
    cursor = conn.cursor()
    
    if user_email:
        cursor.execute('SELECT DISTINCT portfolio_name FROM portfolio WHERE user_email = ? ORDER BY portfolio_name', (user_email,))
    else:
        cursor.execute('SELECT DISTINCT portfolio_name FROM portfolio WHERE user_email IS NULL ORDER BY portfolio_name')
        
    rows = cursor.fetchall()
    conn.close()
    
    portfs = [row['portfolio_name'] for row in rows]
    if 'Principal' not in portfs:
        portfs.insert(0, 'Principal')
    return portfs

def get_portfolio(portfolio_name: str = 'Principal', user_email: Optional[str] = None) -> List[Dict[str, Any]]:
    conn = _get_conn()
    cursor = conn.cursor()
    
    if user_email:
        cursor.execute('SELECT * FROM portfolio WHERE portfolio_name = ? AND user_email = ? ORDER BY id', (portfolio_name, user_email))
    else:
        cursor.execute('SELECT * FROM portfolio WHERE portfolio_name = ? AND user_email IS NULL ORDER BY id', (portfolio_name,))
        
    rows = cursor.fetchall()
    conn.close()

    portfolio = []
    for row in rows:
        item = dict(row)
        if item.get('extra_params'):
            extra = json.loads(item['extra_params'])
            item.update(extra)
        item.pop('extra_params', None)
        portfolio.append(item)
    return portfolio

def remove_asset(asset_id: int, user_email: Optional[str] = None):
    conn = _get_conn()
    cursor = conn.cursor()
    
    if user_email:
        cursor.execute('DELETE FROM portfolio WHERE id = ? AND user_email = ?', (asset_id, user_email))
    else:
        cursor.execute('DELETE FROM portfolio WHERE id = ? AND user_email IS NULL', (asset_id,))
        
    conn.commit()
    conn.close()

def clear_portfolio(portfolio_name: str = 'Principal', user_email: Optional[str] = None):
    conn = _get_conn()
    cursor = conn.cursor()
    
    if user_email:
        cursor.execute('DELETE FROM portfolio WHERE portfolio_name = ? AND user_email = ?', (portfolio_name, user_email))
    else:
        cursor.execute('DELETE FROM portfolio WHERE portfolio_name = ? AND user_email IS NULL', (portfolio_name,))
        
    conn.commit()
    conn.close()

# Initialize DB on import
init_db()
