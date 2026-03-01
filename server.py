"""
server.py — Verifiable Wallet Transaction Explainer
70+ EVM chains, known token detection (USDC/USDT/DAI/WETH etc),
direct API fallback for chains behind Etherscan V2 paywall.
"""

import os, json, secrets, traceback, sys, time
import urllib.request, urllib.error
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv
load_dotenv()

app = Flask(__name__, static_folder="public", static_url_path="")
CORS(app)

# ── OpenGradient ─────────────────────────────────────────────
OG_AVAILABLE = False
og = None
try:
    import opengradient as _og
    og = _og; OG_AVAILABLE = True
    print("✅ OpenGradient SDK imported", flush=True)
except Exception as e:
    print(f"⚠️  OpenGradient: {e}", flush=True)

_og_client = None
def get_og_client():
    global _og_client
    if _og_client: return _og_client
    if not OG_AVAILABLE: return None
    pk = os.environ.get("OG_PRIVATE_KEY", "")
    if not pk or "YOUR_PRIVATE_KEY" in pk: return None
    try:
        _og_client = og.Client(private_key=pk)
        try: _og_client.llm.ensure_opg_approval(opg_amount=5.0)
        except: pass
        print("✅ OG client ready", flush=True)
        return _og_client
    except Exception as e:
        print(f"❌ OG: {e}", flush=True); return None


# ══════════════════════════════════════════════════════════════
# KNOWN TOKEN DATABASE — USDC, USDT, WETH, DAI, WBTC etc
# ══════════════════════════════════════════════════════════════

KNOWN_TOKENS = {
    # Ethereum (1)
    "0xdac17f958d2ee523a2206206994597c13d831ec7": ("USDT", 6),
    "0xa0b86991c6218b36c1d19d4a2e9eb0ce3606eb48": ("USDC", 6),
    "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2": ("WETH", 18),
    "0x6b175474e89094c44da98b954eedeac495271d0f": ("DAI", 18),
    "0x2260fac5e5542a773aa44fbcfedf7c193bc2c599": ("WBTC", 8),
    "0x514910771af9ca656af840dff83e8264ecf986ca": ("LINK", 18),
    "0x1f9840a85d5af5bf1d1762f925bdaddc4201f984": ("UNI", 18),
    "0x95ad61b0a150d79219dcf64e1e6cc01f0b64c4ce": ("SHIB", 18),
    "0xae7ab96520de3a18e5e111b5eaab095312d7fe84": ("stETH", 18),
    "0xbe9895146f7af43049ca1c1ae358b0541ea49704": ("cbETH", 18),
    "0x7fc66500c84a76ad7e9c93437bfc5ac33e2ddae9": ("AAVE", 18),
    "0xd533a949740bb3306d119cc777fa900ba034cd52": ("CRV", 18),
    "0x4d224452801aced8b2f0aebe155379bb5d594381": ("APE", 18),
    "0x5a98fcbea516cf06857215779fd812ca3bef1b32": ("LDO", 18),
    "0xc944e90c64b2c07662a292be6244bdf05cda44a7": ("GRT", 18),
    # Base (8453)
    "0x833589fcd6edb6e08f4c7c32d4f71b54bda02913": ("USDC", 6),
    "0xfde4c96c8593536e31f229ea8f37b2ada2699bb2": ("USDT", 6),
    "0x4200000000000000000000000000000000000006": ("WETH", 18),
    "0x50c5725949a6f0c72e6c4a641f24049a917db0cb": ("DAI", 18),
    "0xd9aaec86b65d86f6a7b5b1b0c42ffa531710b6ca": ("USDbC", 6),
    "0x2ae3f1ec7f1f5012cfeab0185bfc7aa3cf0dec22": ("cbETH", 18),
    # Arbitrum (42161)
    "0xaf88d065e77c8cc2239327c5edb3a432268e5831": ("USDC", 6),
    "0xff970a61a04b1ca14834a43f5de4533ebddb5cc8": ("USDC.e", 6),
    "0xfd086bc7cd5c481dcc9c85ebe478a1c0b69fcbb9": ("USDT", 6),
    "0x82af49447d8a07e3bd95bd0d56f35241523fbab1": ("WETH", 18),
    "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1": ("DAI", 18),
    "0x2f2a2543b76a4166549f7aab2e75bef0aefc5b0f": ("WBTC", 8),
    # Optimism (10)
    "0x0b2c639c533813f4aa9d7837caf62653d097ff85": ("USDC", 6),
    "0x7f5c764cbc14f9669b88837ca1490cca17c31607": ("USDC.e", 6),
    "0x94b008aa00579c1307b0ef2c499ad98a8ce58e58": ("USDT", 6),
    "0xda10009cbd5d07dd0cecc66161fc93d7c9000da1": ("DAI", 18),
    # Polygon (137)
    "0x3c499c542cef5e3811e1192ce70d8cc03d5c3359": ("USDC", 6),
    "0x2791bca1f2de4661ed88a30c99a7a9449aa84174": ("USDC.e", 6),
    "0xc2132d05d31c914a87c6611c10748aeb04b58e8f": ("USDT", 6),
    "0x7ceb23fd6bc0add59e62ac25578270cff1b9f619": ("WETH", 18),
    "0x0d500b1d8e8ef31e21c99d1db9a6444d3adf1270": ("WMATIC", 18),
    "0x8f3cf7ad23cd3cadbd9735aff958023239c6a063": ("DAI", 18),
    "0x1bfd67037b42cf73acf2047067bd4f2c47d9bfd6": ("WBTC", 8),
    # BNB Chain (56)
    "0x55d398326f99059ff775485246999027b3197955": ("USDT", 18),
    "0x8ac76a51cc950d9822d68b83fe1ad97b32cd580d": ("USDC", 18),
    "0xbb4cdb9cbd36b01bd1cbaebf2de08d9173bc095c": ("WBNB", 18),
    "0x1af3f329e8be154074d8769d1ffa4ee058b1dbc3": ("DAI", 18),
    "0x2170ed0880ac9a755fd29b2688956bd959f933f8": ("ETH", 18),
    "0x7130d2a12b9bcbfae4f2634d864a1ee1ce3ead9c": ("BTCB", 18),
    # Avalanche (43114)
    "0xb97ef9ef8734c71904d8002f8b6bc66dd9c48a6e": ("USDC", 6),
    "0x9702230a8ea53601f5cd2dc00fdbc13d4df4a8c7": ("USDT", 6),
    "0xb31f66aa3c1e785363f0875a1b74e27b85fd66c7": ("WAVAX", 18),
    "0x49d5c2bdffac6ce2bfdb6640f4f80f226bc10bab": ("WETH.e", 18),
    # Linea (59144)
    "0x176211869ca2b568f2a7d4ee941e073a821ee1ff": ("USDC", 6),
    "0xa219439258ca9da29e9cc4ce5596924745e12b93": ("USDT", 6),
    "0xe5d7c2a44ffddf6b295a15c148167daaaf5cf34f": ("WETH", 18),
    # Scroll (534352)
    "0x06efdbff2a14a7c8e15944d1f4a48f9f95f663a4": ("USDC", 6),
    "0xf55bec9cafdbe8730f096aa55dad6d22d44099df": ("USDT", 6),
    "0x5300000000000000000000000000000000000004": ("WETH", 18),
    # Blast (81457)
    "0x4300000000000000000000000000000000000003": ("USDB", 18),
    "0x4300000000000000000000000000000000000004": ("WETH", 18),
}

def resolve_token(address, raw_amount):
    addr = address.lower()
    info = KNOWN_TOKENS.get(addr)
    if info:
        name, dec = info
        amt = raw_amount / (10 ** dec)
        if amt >= 1_000_000: f = f"{amt:,.0f}"
        elif amt >= 1: f = f"{amt:,.2f}"
        elif amt > 0: f = f"{amt:.6f}"
        else: f = "0"
        return name, f
    # Unknown — guess decimals
    if raw_amount > 1e24: return addr[:10]+"...", f"{raw_amount/1e18:,.4f}"
    elif raw_amount > 1e12: return addr[:10]+"...", f"{raw_amount/1e6:,.2f}"
    else: return addr[:10]+"...", str(raw_amount)


# ══════════════════════════════════════════════════════════════
# CHAIN REGISTRY — Etherscan V2 + Direct API Fallbacks
# ══════════════════════════════════════════════════════════════

ETHERSCAN_KEY = os.environ.get("ETHERSCAN_API_KEY", "")
BASESCAN_KEY = os.environ.get("BASESCAN_API_KEY", "")

# Chains that need direct API (Etherscan V2 free tier blocks them)
DIRECT_API_CHAINS = [
    {"name": "Base",           "chainid": 8453,  "symbol": "ETH",  "explorer": "https://basescan.org",            "api": "https://api.basescan.org/api",            "testnet": False},
    {"name": "OP Mainnet",     "chainid": 10,    "symbol": "ETH",  "explorer": "https://optimistic.etherscan.io", "api": "https://api-optimistic.etherscan.io/api",  "testnet": False},
    {"name": "BNB Smart Chain","chainid": 56,    "symbol": "BNB",  "explorer": "https://bscscan.com",             "api": "https://api.bscscan.com/api",              "testnet": False},
    {"name": "Avalanche C",    "chainid": 43114, "symbol": "AVAX", "explorer": "https://snowscan.xyz",            "api": "https://api.snowscan.xyz/api",             "testnet": False},
    {"name": "Base Sepolia",   "chainid": 84532, "symbol": "ETH",  "explorer": "https://sepolia.basescan.org",    "api": "https://api-sepolia.basescan.org/api",     "testnet": True},
    {"name": "OP Sepolia",     "chainid": 11155420,"symbol":"ETH", "explorer": "https://sepolia-optimistic.etherscan.io","api":"https://api-sepolia-optimistic.etherscan.io/api","testnet": True},
    {"name": "BNB Testnet",    "chainid": 97,    "symbol": "tBNB", "explorer": "https://testnet.bscscan.com",     "api": "https://api-testnet.bscscan.com/api",      "testnet": True},
    {"name": "Avalanche Fuji", "chainid": 43113, "symbol": "AVAX", "explorer": "https://testnet.snowscan.xyz",    "api": "https://api-testnet.snowscan.xyz/api",     "testnet": True},
]

# Chains that work with Etherscan V2 free tier
V2_CHAINS = [
    {"name": "Ethereum",       "chainid": 1,         "symbol": "ETH",   "explorer": "https://etherscan.io",              "testnet": False},
    {"name": "Arbitrum One",   "chainid": 42161,      "symbol": "ETH",   "explorer": "https://arbiscan.io",               "testnet": False},
    {"name": "Polygon",        "chainid": 137,        "symbol": "POL",   "explorer": "https://polygonscan.com",           "testnet": False},
    {"name": "Linea",          "chainid": 59144,      "symbol": "ETH",   "explorer": "https://lineascan.build",           "testnet": False},
    {"name": "Blast",          "chainid": 81457,      "symbol": "ETH",   "explorer": "https://blastscan.io",              "testnet": False},
    {"name": "Scroll",         "chainid": 534352,     "symbol": "ETH",   "explorer": "https://scrollscan.com",            "testnet": False},
    {"name": "Mantle",         "chainid": 5000,       "symbol": "MNT",   "explorer": "https://mantlescan.xyz",            "testnet": False},
    {"name": "Celo",           "chainid": 42220,      "symbol": "CELO",  "explorer": "https://celoscan.io",               "testnet": False},
    {"name": "Gnosis",         "chainid": 100,        "symbol": "xDAI",  "explorer": "https://gnosisscan.io",             "testnet": False},
    {"name": "Fraxtal",        "chainid": 252,        "symbol": "frxETH","explorer": "https://fraxscan.com",              "testnet": False},
    {"name": "Moonbeam",       "chainid": 1284,       "symbol": "GLMR",  "explorer": "https://moonbeam.moonscan.io",      "testnet": False},
    {"name": "Moonriver",      "chainid": 1285,       "symbol": "MOVR",  "explorer": "https://moonriver.moonscan.io",     "testnet": False},
    {"name": "opBNB",          "chainid": 204,        "symbol": "BNB",   "explorer": "https://opbnb.bscscan.com",         "testnet": False},
    {"name": "Taiko",          "chainid": 167000,     "symbol": "ETH",   "explorer": "https://taikoscan.io",              "testnet": False},
    {"name": "BitTorrent",     "chainid": 199,        "symbol": "BTT",   "explorer": "https://bttcscan.com",              "testnet": False},
    {"name": "XDC",            "chainid": 50,         "symbol": "XDC",   "explorer": "https://xdcscan.io",                "testnet": False},
    {"name": "ApeChain",       "chainid": 33139,      "symbol": "APE",   "explorer": "https://apescan.io",                "testnet": False},
    {"name": "World",          "chainid": 480,        "symbol": "ETH",   "explorer": "https://worldscan.org",             "testnet": False},
    {"name": "Sonic",          "chainid": 146,        "symbol": "S",     "explorer": "https://sonicscan.org",             "testnet": False},
    {"name": "Unichain",       "chainid": 130,        "symbol": "ETH",   "explorer": "https://uniscan.xyz",               "testnet": False},
    {"name": "Abstract",       "chainid": 2741,       "symbol": "ETH",   "explorer": "https://abscan.org",                "testnet": False},
    {"name": "Berachain",      "chainid": 80094,      "symbol": "BERA",  "explorer": "https://berascan.com",              "testnet": False},
    {"name": "Swellchain",     "chainid": 1923,       "symbol": "ETH",   "explorer": "https://swellscan.io",              "testnet": False},
    {"name": "Monad",          "chainid": 143,        "symbol": "MON",   "explorer": "https://monadscan.com",             "testnet": False},
    {"name": "HyperEVM",       "chainid": 999,        "symbol": "HYPE",  "explorer": "https://hyperscan.xyz",             "testnet": False},
    {"name": "Katana",         "chainid": 747474,     "symbol": "ETH",   "explorer": "https://katanascan.xyz",            "testnet": False},
    {"name": "Sei",            "chainid": 1329,       "symbol": "SEI",   "explorer": "https://seiscan.io",                "testnet": False},
    {"name": "Memecore",       "chainid": 4352,       "symbol": "MEM",   "explorer": "https://memecorescan.io",           "testnet": False},
    {"name": "Stable",         "chainid": 988,        "symbol": "STB",   "explorer": "https://stablescan.xyz",            "testnet": False},
    {"name": "Plasma",         "chainid": 9745,       "symbol": "ETH",   "explorer": "https://plasmascan.io",             "testnet": False},
    {"name": "MegaETH",        "chainid": 4326,       "symbol": "ETH",   "explorer": "https://megaethscan.io",            "testnet": False},
    # Testnets (V2 free)
    {"name": "Sepolia",           "chainid": 11155111, "symbol": "ETH",  "explorer": "https://sepolia.etherscan.io",       "testnet": True},
    {"name": "Hoodi",             "chainid": 560048,   "symbol": "ETH",  "explorer": "https://hoodi.etherscan.io",         "testnet": True},
    {"name": "Arbitrum Sepolia",  "chainid": 421614,   "symbol": "ETH",  "explorer": "https://sepolia.arbiscan.io",        "testnet": True},
    {"name": "Polygon Amoy",     "chainid": 80002,    "symbol": "POL",  "explorer": "https://amoy.polygonscan.com",       "testnet": True},
    {"name": "Linea Sepolia",    "chainid": 59141,    "symbol": "ETH",  "explorer": "https://sepolia.lineascan.build",    "testnet": True},
    {"name": "Blast Sepolia",    "chainid": 168587773,"symbol": "ETH",  "explorer": "https://sepolia.blastscan.io",       "testnet": True},
    {"name": "Scroll Sepolia",   "chainid": 534351,   "symbol": "ETH",  "explorer": "https://sepolia.scrollscan.com",     "testnet": True},
    {"name": "Mantle Sepolia",   "chainid": 5003,     "symbol": "MNT",  "explorer": "https://sepolia.mantlescan.xyz",     "testnet": True},
    {"name": "Celo Sepolia",     "chainid": 11142220, "symbol": "CELO", "explorer": "https://sepolia.celoscan.io",        "testnet": True},
    {"name": "Fraxtal Hoodi",    "chainid": 2523,     "symbol": "frxETH","explorer": "https://hoodi.fraxscan.com",        "testnet": True},
    {"name": "Moonbase Alpha",   "chainid": 1287,     "symbol": "DEV",  "explorer": "https://moonbase.moonscan.io",       "testnet": True},
    {"name": "opBNB Testnet",    "chainid": 5611,     "symbol": "tBNB", "explorer": "https://testnet.opbnb.bscscan.com",  "testnet": True},
    {"name": "Taiko Hoodi",      "chainid": 167013,   "symbol": "ETH",  "explorer": "https://hoodi.taikoscan.io",         "testnet": True},
    {"name": "BitTorrent Test",  "chainid": 1029,     "symbol": "BTT",  "explorer": "https://testnet.bttcscan.com",       "testnet": True},
    {"name": "XDC Apothem",      "chainid": 51,       "symbol": "XDC",  "explorer": "https://apothem.xdcscan.io",         "testnet": True},
    {"name": "ApeChain Curtis",  "chainid": 33111,    "symbol": "APE",  "explorer": "https://curtis.apescan.io",          "testnet": True},
    {"name": "World Sepolia",    "chainid": 4801,     "symbol": "ETH",  "explorer": "https://sepolia.worldscan.org",      "testnet": True},
    {"name": "Sonic Testnet",    "chainid": 14601,    "symbol": "S",    "explorer": "https://testnet.sonicscan.org",      "testnet": True},
    {"name": "Unichain Sepolia", "chainid": 1301,     "symbol": "ETH",  "explorer": "https://sepolia.uniscan.xyz",        "testnet": True},
    {"name": "Abstract Sepolia", "chainid": 11124,    "symbol": "ETH",  "explorer": "https://sepolia.abscan.org",         "testnet": True},
    {"name": "Berachain Bepolia","chainid": 80069,    "symbol": "BERA", "explorer": "https://bepolia.berascan.com",       "testnet": True},
    {"name": "Swellchain Test",  "chainid": 1924,     "symbol": "ETH",  "explorer": "https://testnet.swellscan.io",       "testnet": True},
    {"name": "Monad Testnet",    "chainid": 10143,    "symbol": "MON",  "explorer": "https://testnet.monadscan.com",      "testnet": True},
    {"name": "Katana Bokuto",    "chainid": 737373,   "symbol": "ETH",  "explorer": "https://bokuto.katanascan.xyz",      "testnet": True},
    {"name": "Sei Testnet",      "chainid": 1328,     "symbol": "SEI",  "explorer": "https://testnet.seiscan.io",         "testnet": True},
    {"name": "Memecore Test",    "chainid": 43521,    "symbol": "MEM",  "explorer": "https://testnet.memecorescan.io",    "testnet": True},
    {"name": "Stable Testnet",   "chainid": 2201,     "symbol": "STB",  "explorer": "https://testnet.stablescan.xyz",     "testnet": True},
    {"name": "Plasma Testnet",   "chainid": 9746,     "symbol": "ETH",  "explorer": "https://testnet.plasmascan.io",      "testnet": True},
    {"name": "MegaETH Testnet",  "chainid": 6342,     "symbol": "ETH",  "explorer": "https://testnet.megaethscan.io",     "testnet": True},
]

ALL_CHAINS = DIRECT_API_CHAINS + V2_CHAINS
print(f"📡 {len(ALL_CHAINS)} chains ({len(DIRECT_API_CHAINS)} direct + {len(V2_CHAINS)} v2)", flush=True)


# ── Fetch Helpers ────────────────────────────────────────────

def _http_get(url, timeout=6):
    req = urllib.request.Request(url, headers={"User-Agent": "WalletExplainer/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())

def _parse_tx(result, receipt, chain):
    val_wei = int(result.get("value","0x0"),16)
    val = val_wei/1e18
    gp_wei = int(result.get("gasPrice","0x0"),16)
    gp_gwei = gp_wei/1e9
    blk = int(result.get("blockNumber","0x0"),16)
    gas_used = int(receipt.get("gasUsed","0x0"),16) if receipt else int(result.get("gas","0x0"),16)
    status = "Success" if receipt and receipt.get("status")=="0x1" else "Failed"
    gas_fee = (gas_used*gp_wei)/1e18
    sym = chain["symbol"]

    # Token transfers
    transfers = []
    topic = "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef"
    for log in (receipt.get("logs",[]) if receipt else []):
        tops = log.get("topics",[])
        if tops and tops[0]==topic and len(tops)>=3:
            raw = int(log.get("data","0x0"),16)
            name, amt = resolve_token(log.get("address",""), raw)
            transfers.append({"token":name,"amount":amt,"from":"0x"+tops[1][-40:],"to":"0x"+tops[2][-40:],"contract":log.get("address","")})

    return {
        "hash": result.get("hash",""), "from": result.get("from","unknown"),
        "to": result.get("to") or "Contract Creation",
        "value": f"{val:.6f} {sym}" if val>0 else f"0 {sym}",
        "gasUsed": gas_used, "gasPrice": f"{gp_gwei:.2f} gwei",
        "gasFeeETH": f"{gas_fee:.6f} {sym}", "blockNumber": blk,
        "status": status, "chain": chain["name"],
        "chainExplorer": f"{chain['explorer']}/tx/{result.get('hash','')}",
        "symbol": sym, "isTestnet": chain.get("testnet",False),
        "tokenTransfers": transfers[:10],
        "isContractCall": result.get("input","0x")!="0x",
        "inputData": result.get("input","0x")[:100],
        "nonce": int(result.get("nonce","0x0"),16),
    }


def fetch_direct(tx_hash, chain):
    """Fetch via chain's own API (for Base, OP, BNB, AVAX)."""
    api = chain["api"]
    key = BASESCAN_KEY or ETHERSCAN_KEY or "YourApiKeyToken"
    try:
        d = _http_get(f"{api}?module=proxy&action=eth_getTransactionByHash&txhash={tx_hash}&apikey={key}")
        result = d.get("result")
        if not result or isinstance(result, str): return None
        d2 = _http_get(f"{api}?module=proxy&action=eth_getTransactionReceipt&txhash={tx_hash}&apikey={key}")
        receipt = d2.get("result",{})
        return _parse_tx(result, receipt, chain)
    except: return None


def fetch_v2(tx_hash, chain):
    """Fetch via Etherscan V2 unified API."""
    key = ETHERSCAN_KEY or "YourApiKeyToken"
    cid = chain["chainid"]
    try:
        d = _http_get(f"https://api.etherscan.io/v2/api?chainid={cid}&module=proxy&action=eth_getTransactionByHash&txhash={tx_hash}&apikey={key}")
        result = d.get("result")
        if not result or isinstance(result, str): return None
        d2 = _http_get(f"https://api.etherscan.io/v2/api?chainid={cid}&module=proxy&action=eth_getTransactionReceipt&txhash={tx_hash}&apikey={key}")
        receipt = d2.get("result",{})
        return _parse_tx(result, receipt, chain)
    except: return None


def fetch_real_transaction(tx_hash):
    print(f"📡 Searching {len(ALL_CHAINS)} chains...", flush=True)

    # 1. Direct API chains first (Base, OP, BNB, AVAX) — these fail on V2 free tier
    for c in DIRECT_API_CHAINS:
        r = fetch_direct(tx_hash, c)
        if r:
            print(f"✅ {c['name']} (direct API)", flush=True)
            return r

    # 2. V2 chains
    v2_main = [c for c in V2_CHAINS if not c.get("testnet")]
    v2_test = [c for c in V2_CHAINS if c.get("testnet")]

    for c in v2_main[:5]:  # Priority mainnets
        r = fetch_v2(tx_hash, c)
        if r:
            print(f"✅ {c['name']} (v2)", flush=True)
            return r

    for c in v2_test:  # Testnets
        r = fetch_v2(tx_hash, c)
        if r:
            print(f"✅ {c['name']} (v2 testnet)", flush=True)
            return r

    for c in v2_main[5:]:  # Remaining mainnets
        r = fetch_v2(tx_hash, c)
        if r:
            print(f"✅ {c['name']} (v2)", flush=True)
            return r

    print("⚠️  Not found", flush=True)
    return None


def get_fallback(h):
    return {"hash":h,"from":"unknown","to":"unknown","value":"unknown","gasUsed":0,
            "gasPrice":"unknown","gasFeeETH":"unknown","blockNumber":0,"status":"Not Found",
            "chain":"Unknown","chainExplorer":"","symbol":"ETH","isTestnet":False,
            "tokenTransfers":[],"isContractCall":False,"inputData":"0x","nonce":0}


# ── OpenGradient AI ──────────────────────────────────────────

def call_og(prompt):
    client = get_og_client()
    if not client: return None
    try:
        r = client.llm.chat(model=og.TEE_LLM.GEMINI_2_5_FLASH,
            messages=[{"role":"system","content":"You are a blockchain analyst. Explain transactions for beginners. Use ## headers and **bold**."},
                      {"role":"user","content":prompt}],
            max_tokens=600, temperature=0.3)
        co = r.chat_output
        ex = co.get("content",str(co)) if isinstance(co,dict) else str(co)
        return {"explanation":ex,"payment_hash":getattr(r,"payment_hash",None)} if ex else None
    except Exception as e:
        print(f"❌ LLM: {e}", flush=True); return None

def analyze(tx):
    chain = tx.get("chain","Unknown")
    explorer = tx.get("chainExplorer","")
    test = tx.get("isTestnet",False)
    trs = tx.get("tokenTransfers",[])
    tr_txt = ""
    if trs:
        lines = [f"- {t['amount']} {t['token']} → {t['to'][:12]}..." for t in trs]
        tr_txt = "\nToken transfers:\n"+"\n".join(lines)

    prompt = f"""Explain this {'testnet ' if test else ''}transaction from **{chain}** simply.

Sections: SUMMARY, CHAIN INFO{' (TESTNET=test money)' if test else ''}, DETAILS, TOKEN TRANSFERS, GAS FEES, SUSPICION CHECK
{"Smart contract call." if tx.get("isContractCall") else "Simple transfer."}
{tr_txt}
Explorer: {explorer}
Use ## headers, **bold**.

{json.dumps(tx, indent=2)}"""

    r = call_og(prompt)
    if r:
        ph = r.get("payment_hash")
        return {"explanation":r["explanation"],"proof":{"paymentHash":ph or "verified-no-settlement",
            "model":"GEMINI_2_5_FLASH","verifiedByTEE":True,
            "explorerUrl":f"https://explorer.opengradient.ai/tx/{ph}" if ph else "https://explorer.opengradient.ai",
            "settlementNetwork":"Base Sepolia","inferenceNetwork":"OpenGradient","mode":"LIVE"}}
    return {"explanation":f"## {chain}\n**{tx['from'][:12]}...** → **{tx['to'][:12]}...**\nValue: **{tx['value']}** | Status: {tx['status']}\n\n⚠️ AI unavailable.",
            "proof":{"paymentHash":"0x"+secrets.token_hex(32),"model":"fallback","verifiedByTEE":False,
            "explorerUrl":"https://explorer.opengradient.ai","settlementNetwork":"Base Sepolia",
            "inferenceNetwork":"OpenGradient Testnet","mode":"MOCK"}}


# ── Routes ───────────────────────────────────────────────────

@app.route("/")
def index(): return send_from_directory("public","index.html")

@app.route("/<path:path>")
def static_files(path): return send_from_directory("public",path)

@app.route("/analyze-transaction", methods=["POST","OPTIONS"])
def analyze_transaction():
    if request.method=="OPTIONS": return "",200
    try:
        data = request.get_json()
        h = data.get("txHash","").strip() if data else ""
        if not h: return jsonify({"error":"Provide a hash."}),400
        if not h.startswith("0x") or len(h)<10: return jsonify({"error":"Invalid hash."}),400
        print(f"\n{'='*50}\n🔍 {h}", flush=True)
        tx = fetch_real_transaction(h) or get_fallback(h)
        a = analyze(tx)
        print(f"📤 {a['proof']['mode']} | {tx.get('chain','?')}\n{'='*50}", flush=True)
        return jsonify({"success":True,
            "transaction":{"hash":tx["hash"],"from":tx["from"],"to":tx["to"],"value":tx["value"],
                "gasUsed":tx["gasUsed"],"gasPrice":tx["gasPrice"],"gasFee":tx["gasFeeETH"],
                "status":tx["status"],"block":tx["blockNumber"],"chain":tx.get("chain","Unknown"),
                "chainExplorer":tx.get("chainExplorer",""),"isTestnet":tx.get("isTestnet",False),
                "tokenTransfers":tx.get("tokenTransfers",[])},
            "explanation":a["explanation"],"proof":a["proof"]})
    except Exception as e:
        print(f"❌ {e}", flush=True); traceback.print_exc()
        return jsonify({"error":"Something went wrong."}),500

@app.route("/chains")
def chains_list():
    return jsonify({"total":len(ALL_CHAINS),
        "chains":[{"name":c["name"],"chainid":c["chainid"],"symbol":c["symbol"],"testnet":c.get("testnet",False)} for c in ALL_CHAINS]})

@app.route("/debug")
def debug():
    pk = os.environ.get("OG_PRIVATE_KEY","")
    return jsonify({"sdk":OG_AVAILABLE,"key":f"{pk[:8]}..." if pk and "YOUR" not in pk else "NOT SET",
        "etherscan_key":"SET" if ETHERSCAN_KEY else "NOT SET",
        "basescan_key":"SET" if BASESCAN_KEY else "USING ETHERSCAN KEY",
        "chains":len(ALL_CHAINS)})

if __name__=="__main__":
    port = int(os.environ.get("PORT",10000))
    print(f"🛡️  http://0.0.0.0:{port} | SDK:{OG_AVAILABLE} | {len(ALL_CHAINS)} chains", flush=True)
    app.run(host="0.0.0.0", port=port, debug=False)
