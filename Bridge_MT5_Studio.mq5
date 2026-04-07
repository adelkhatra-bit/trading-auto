//+------------------------------------------------------------------+
//|                                            Bridge_MT5_Studio.mq5 |
//|                   Clean multi-symbol MT5 -> Node bridge (/mt5)   |
//+------------------------------------------------------------------+
#property strict
#property version   "4.0"
#property description "Publie les ticks multi-symboles vers http://127.0.0.1:4000/mt5"

input string SERVER_URL = "http://127.0.0.1:4000/mt5";
input int    SEND_INTERVAL_MS = 1000;
input bool   USE_MARKETWATCH = true;
input int    MAX_SYMBOLS_PER_CYCLE = 20;
input bool   INCLUDE_M1_OHLC = true;
input bool   INCLUDE_HISTORY = true;
input int    HISTORY_BARS = 60;
input int    HISTORY_REFRESH_SEC = 15;
input bool   DEBUG_LOG = false;

uint g_lastTickMs = 0;
int  g_sent = 0;
int  g_failed = 0;
int  g_roundRobinStart = 0;
string g_histSymbols[512];
datetime g_histSentAt[512];
int g_histCount = 0;

int GetHistorySlot(string symbol)
{
   for(int i = 0; i < g_histCount; i++)
   {
      if(g_histSymbols[i] == symbol)
         return i;
   }

   if(g_histCount >= 512)
      return -1;

   g_histSymbols[g_histCount] = symbol;
   g_histSentAt[g_histCount] = 0;
   g_histCount++;
   return (g_histCount - 1);
}

bool ShouldAttachHistory(string symbol)
{
   if(!INCLUDE_HISTORY)
      return false;

   int slot = GetHistorySlot(symbol);
   if(slot < 0)
      return false;

   datetime nowTs = TimeCurrent();
   if(g_histSentAt[slot] == 0 || (nowTs - g_histSentAt[slot]) >= HISTORY_REFRESH_SEC)
   {
      g_histSentAt[slot] = nowTs;
      return true;
   }

   return false;
}

string BuildHistoryJson(string symbol, int bars)
{
   MqlRates rates[];
   int need = MathMax(10, bars);
   int copied = CopyRates(symbol, PERIOD_M1, 0, need, rates);
   if(copied < 10)
      return "";

   int digits = (int)SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   if(digits < 0) digits = 5;

   string out = ",\"history\":[";
   bool first = true;

   // CopyRates returns most recent first; reverse to oldest->newest
   for(int i = copied - 1; i >= 0; i--)
   {
      long tMs = (long)rates[i].time * 1000;
      string row = StringFormat(
         "{\"time\":%I64d,\"open\":%s,\"high\":%s,\"low\":%s,\"close\":%s,\"volume\":%I64d}",
         tMs,
         DoubleToString(rates[i].open, digits),
         DoubleToString(rates[i].high, digits),
         DoubleToString(rates[i].low, digits),
         DoubleToString(rates[i].close, digits),
         (long)rates[i].tick_volume
      );
      if(!first) out += ",";
      out += row;
      first = false;
   }

   out += "]";
   return out;
}

//+------------------------------------------------------------------+
//| Initialization                                                   |
//+------------------------------------------------------------------+
int OnInit()
{
   if(SEND_INTERVAL_MS < 200)
   {
      Print("[BRIDGE] SEND_INTERVAL_MS trop bas (min 200)");
      return(INIT_PARAMETERS_INCORRECT);
   }

   EventSetMillisecondTimer(SEND_INTERVAL_MS);
   Print("[BRIDGE] Start v4.0");
   Print("[BRIDGE] URL: ", SERVER_URL);
   Print("[BRIDGE] Interval: ", SEND_INTERVAL_MS, " ms");
   Print("[BRIDGE] Source symboles: ", (USE_MARKETWATCH ? "MarketWatch" : "AllSymbols"));
   return(INIT_SUCCEEDED);
}

//+------------------------------------------------------------------+
//| Deinitialization                                                 |
//+------------------------------------------------------------------+
void OnDeinit(const int reason)
{
   EventKillTimer();
   Print("[BRIDGE] Stop | sent=", g_sent, " failed=", g_failed);
}

//+------------------------------------------------------------------+
//| Keep OnTick light; timer handles scheduled publishing            |
//+------------------------------------------------------------------+
void OnTick()
{
   // Intentionally empty: we use timer for deterministic cadence.
}

//+------------------------------------------------------------------+
//| Timer loop                                                       |
//+------------------------------------------------------------------+
void OnTimer()
{
   PublishBatch();
}

//+------------------------------------------------------------------+
//| Publish a round-robin batch of symbols                           |
//+------------------------------------------------------------------+
void PublishBatch()
{
   int total = SymbolsTotal(USE_MARKETWATCH);
   if(total <= 0)
   {
      if(DEBUG_LOG) Print("[BRIDGE] Aucun symbole detecte.");
      return;
   }

   int toSend = MathMin(MAX_SYMBOLS_PER_CYCLE, total);
   if(toSend <= 0) return;

   for(int n = 0; n < toSend; n++)
   {
      int idx = (g_roundRobinStart + n) % total;
      string symbol = SymbolName(idx, USE_MARKETWATCH);
      if(symbol == "") continue;

      // Ensure symbol subscription if scanning all symbols.
      if(!USE_MARKETWATCH)
         SymbolSelect(symbol, true);

      double bid = SymbolInfoDouble(symbol, SYMBOL_BID);
      double ask = SymbolInfoDouble(symbol, SYMBOL_ASK);
      if(bid <= 0 || ask <= 0)
         continue;

      double price = (bid + ask) / 2.0;
      long tsMs = (long)TimeCurrent() * 1000;
      double vol = SymbolInfoDouble(symbol, SYMBOL_VOLUME_REAL);

      string ohlcPart = "";
      if(INCLUDE_M1_OHLC)
      {
         double o = iOpen(symbol, PERIOD_M1, 0);
         double h = iHigh(symbol, PERIOD_M1, 0);
         double l = iLow(symbol, PERIOD_M1, 0);
         double c = iClose(symbol, PERIOD_M1, 0);

         if(o > 0 && h > 0 && l > 0 && c > 0)
         {
            ohlcPart = StringFormat(
               ",\"ohlc\":{\"open\":%s,\"high\":%s,\"low\":%s,\"close\":%s}",
               DoubleToString(o, 8),
               DoubleToString(h, 8),
               DoubleToString(l, 8),
               DoubleToString(c, 8)
            );
         }
      }

      string historyPart = "";
      if(ShouldAttachHistory(symbol))
      {
         historyPart = BuildHistoryJson(symbol, HISTORY_BARS);
         if(DEBUG_LOG && historyPart != "")
            Print("[BRIDGE] history sent for ", symbol, " bars=", HISTORY_BARS);
      }

      string payload = StringFormat(
         "{\"symbol\":\"%s\",\"bid\":%s,\"ask\":%s,\"price\":%s,\"volume\":%s,\"timeframe\":\"M1\",\"timestamp\":%I64d%s%s}",
         symbol,
         DoubleToString(bid, 8),
         DoubleToString(ask, 8),
         DoubleToString(price, 8),
         DoubleToString(vol, 2),
         tsMs,
         ohlcPart,
         historyPart
      );

      SendData(payload, symbol, price);
   }

   g_roundRobinStart = (g_roundRobinStart + toSend) % total;
}

//+------------------------------------------------------------------+
//| HTTP POST to backend                                             |
//+------------------------------------------------------------------+
void SendData(string data, string symbol, double price)
{
   char post[];
   char result[];
   string reqHeaders = "Content-Type: application/json\r\n";
   string respHeaders = "";

   int len = StringToCharArray(data, post, 0, WHOLE_ARRAY, CP_UTF8);
   if(len <= 0)
   {
      g_failed++;
      if(DEBUG_LOG) Print("[BRIDGE] StringToCharArray failed for ", symbol);
      return;
   }

   // Remove trailing null terminator for clean JSON body.
   ArrayResize(post, len - 1);

   int timeout = 2000;
   int httpCode = WebRequest("POST", SERVER_URL, reqHeaders, timeout, post, result, respHeaders);

   if(httpCode == -1)
   {
      g_failed++;
      int err = GetLastError();
      if(DEBUG_LOG)
         Print("[BRIDGE] ERROR ", err, " send ", symbol, " @", DoubleToString(price, 5));
      ResetLastError();
      return;
   }

   if(httpCode >= 200 && httpCode < 300)
   {
      g_sent++;
      if(DEBUG_LOG && (g_sent % 25 == 0))
         Print("[BRIDGE] OK sent=", g_sent, " failed=", g_failed);
   }
   else
   {
      g_failed++;
      if(DEBUG_LOG)
         Print("[BRIDGE] HTTP ", httpCode, " symbol=", symbol);
   }
}
