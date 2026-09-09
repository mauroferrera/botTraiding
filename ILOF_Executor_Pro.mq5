//+------------------------------------------------------------------+
//|                                ILOF_Executor_Pro.mq5             |
//|              Bot de ejecución rápida con botonera (HUD)          |
//|                 Config trading ILOF: 0.5% riesgo · SL 12 · T1:2  |
//|                                   Copyright 2026, ILOF Exec Pro  |
//+------------------------------------------------------------------+
#property copyright   "ILOF Executive Pro"
#property link        "https://www.mql5.com"
#property version     "1.00"
#property description "Botonera rapida con config ILOF: riesgo 0.5%, SL 12 pips, TP = SL x 2, max 3/dia (compartido con el bot por magic 8882026)."

#include <Trade\Trade.mqh>
#include <Trade\PositionInfo.mqh>
#include <Trade\AccountInfo.mqh>
#include <Trade\SymbolInfo.mqh>

CTrade        trade;
CPositionInfo posInfo;
CSymbolInfo   symInfo;
CAccountInfo  accInfo;

enum ENUM_HUD_THEME
  {
   THEME_DARK_PRO,    // Dark Obsidian Pro
   THEME_NAVY_CYBER   // Navy Blue Cyber
  };

//--- INPUTS: CONFIG TRADING ILOF (dashboard app.py / strategy.yaml)
input group "=== 1. CONFIG TRADING (ILOF) ==="
input double   InpRiskPercent          = 0.5;         // Riesgo por Operacion (%)
input double   InpAccountSize          = 100000.0;    // Tamano Base de Cuenta ($)
input ulong    InpMagicNumber          = 8882026;     // Magic Number (compartido con el bot)
input int      InpSlippagePoints       = 15;          // Desviacion Max (Puntos)
input string   InpComment              = "ILOF Exec"; // Comentario de la Orden

input group "=== 2. SL Y TP (R:R) ==="
input double   InpDefaultSLPips        = 12.0;        // SL por Defecto (Pips)
input double   InpTPRatioR             = 2.0;         // Ratio TP = SL x R (TP = SL * Ratio)

input group "=== 3. LIMITES DIARIOS ==="
input int      InpMaxDailyTrades       = 3;           // Max Operaciones Diarias (1 magic: EA + bot + manual)
input double   InpMaxDailyLossUSD      = 1250.0;      // Limite Max Daily Loss ($)

input group "=== 4. PIP SIZE ==="
input double   InpPipSizeOverride      = 0.0;         // Override de Pip ($) - 0 = Auto (forex/JPY/metales/indices)

input group "=== 5. AUTOGESTION (OJO: re-modifica el SL del magic compartido) ==="
input bool     InpAutoBreakEven        = false;       // Break-Even para posiciones del magic (por defecto OFF)
input double   InpBERatio              = 1.5;         // Ratio R:R para BE
input double   InpBEBufferPips         = 1.0;         // Pips de Ganancia en BE
input bool     InpUseTrailingStop      = false;       // Trailing Stop (por defecto OFF)
input double   InpTrailingDistancePips = 15.0;        // Distancia del SL detras del precio
input double   InpTrailingStepPips     = 2.0;         // Paso minimo para actualizar el SL

input group "=== 6. DASHBOARD (BOTONERA) ==="
input int      InpHUD_X                = 20;          // Posicion X (px)
input int      InpHUD_Y                = 40;          // Posicion Y (px)
input int      InpHUD_Width            = 350;         // Ancho (px)
input int      InpHUD_Height           = 320;         // Alto (px)
input ENUM_HUD_THEME InpTheme          = THEME_DARK_PRO;

//--- GLOBALES
double   g_initialDailyBalance = 0.0;
int      g_dailyTradesCount    = 0;
bool     g_isDailyLocked       = false;
string   g_lockReason          = "OPERATIVO";
datetime g_currentTradingDay   = 0;
bool     g_hudInitialized      = false;

#define HUD_PREFIX "ILOF_HUD_"

//+------------------------------------------------------------------+
//| OnInit                                                           |
//+------------------------------------------------------------------+
int OnInit()
  {
   if(!symInfo.Name(_Symbol)) return(INIT_FAILED);
   symInfo.Refresh();

   trade.SetExpertMagicNumber(InpMagicNumber);
   trade.SetDeviationInPoints(InpSlippagePoints);
   trade.SetTypeFillingBySymbol(_Symbol);

   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   dt.hour = 0; dt.min = 0; dt.sec = 0;
   g_currentTradingDay   = StructToTime(dt);
   g_initialDailyBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(g_initialDailyBalance <= 0) g_initialDailyBalance = InpAccountSize;

   CheckDailyLimits();
   CreateHUD();
   UpdateHUD();
   EventSetTimer(1);

   ChartRedraw(0);
   return(INIT_SUCCEEDED);
  }

//+------------------------------------------------------------------+
//| OnDeinit                                                         |
//+------------------------------------------------------------------+
void OnDeinit(const long reason)
  {
   EventKillTimer();
   DestroyHUD();
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| OnTick                                                           |
//+------------------------------------------------------------------+
void OnTick()
  {
   symInfo.RefreshRates();
   ManagePositionsSL();
   CheckDailyLimits();
   UpdateHUD();
  }

//+------------------------------------------------------------------+
//| OnTimer                                                          |
//+------------------------------------------------------------------+
void OnTimer()
  {
   MqlDateTime dt;
   TimeToStruct(TimeCurrent(), dt);
   dt.hour = 0; dt.min = 0; dt.sec = 0;
   datetime todayStart = StructToTime(dt);

   if(todayStart > g_currentTradingDay)
     {
      g_currentTradingDay   = todayStart;
      g_initialDailyBalance = AccountInfoDouble(ACCOUNT_BALANCE);
      if(g_initialDailyBalance <= 0) g_initialDailyBalance = InpAccountSize;
     }

   CheckDailyLimits();
   UpdateHUD();
  }

//+------------------------------------------------------------------+
//| OnChartEvent (solo botones, sin hotkeys)                         |
//+------------------------------------------------------------------+
void OnChartEvent(const int id, const long &lparam, const double &dparam, const string &sparam)
  {
   if(id == CHARTEVENT_OBJECT_CLICK)
     {
      if(sparam == HUD_PREFIX + "BTN_BUY")
        {
         ExecuteMarketOrder(ORDER_TYPE_BUY);
         ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
        }
      else if(sparam == HUD_PREFIX + "BTN_SELL")
        {
         ExecuteMarketOrder(ORDER_TYPE_SELL);
         ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
        }
      else if(sparam == HUD_PREFIX + "BTN_RESET")
        {
         ExecuteManualReset();
         ObjectSetInteger(0, sparam, OBJPROP_STATE, false);
        }
     }
  }

//+------------------------------------------------------------------+
//| Reset Manual: re-ancla balance y re-evalua limites               |
//+------------------------------------------------------------------+
void ExecuteManualReset()
  {
   g_initialDailyBalance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(g_initialDailyBalance <= 0) g_initialDailyBalance = InpAccountSize;
   CheckDailyLimits();
   UpdateHUD();
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Control de Riesgo (conteo real desde historico)                  |
//+------------------------------------------------------------------+
void CheckDailyLimits()
  {
   g_dailyTradesCount = CountTodayTrades();

   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   double dailyPL = equity - g_initialDailyBalance;
   double ddUSD   = (dailyPL < 0) ? -dailyPL : 0.0;

   if(ddUSD >= InpMaxDailyLossUSD)
     {
      g_isDailyLocked = true;
      g_lockReason    = "MAX DAILY LOSS ALCANZADO";
      return;
     }

   if(g_dailyTradesCount >= InpMaxDailyTrades)
     {
      g_isDailyLocked = true;
      g_lockReason    = "MAX " + (string)InpMaxDailyTrades + " TRADES/DIA";
      return;
     }

   g_isDailyLocked = false;
   g_lockReason    = "OPERATIVO";
  }

//+------------------------------------------------------------------+
//| Conteo de operaciones de HOY del magic compartido, desde MT5     |
//+------------------------------------------------------------------+
int CountTodayTrades()
  {
   int count = 0;
   if(!HistorySelect(g_currentTradingDay, TimeCurrent())) return(0);
   int total = HistoryDealsTotal();
   for(int i = total - 1; i >= 0; i--)
     {
      ulong ticket = HistoryDealGetTicket(i);
      if(ticket == 0) continue;
      if(HistoryDealGetInteger(ticket, DEAL_ENTRY) != DEAL_ENTRY_IN) continue;
      if((long)HistoryDealGetInteger(ticket, DEAL_MAGIC) != (long)InpMagicNumber) continue;
      long type = HistoryDealGetInteger(ticket, DEAL_TYPE);
      if(type != DEAL_TYPE_BUY && type != DEAL_TYPE_SELL) continue;
      count++;
     }
   return(count);
  }

//+------------------------------------------------------------------+
//| Calculo Exacto de Pip Size y Lote                                |
//+------------------------------------------------------------------+
double GetPipSize(string symbol)
  {
   if(InpPipSizeOverride > 0) return(InpPipSizeOverride);
   long   digits = SymbolInfoInteger(symbol, SYMBOL_DIGITS);
   double point  = SymbolInfoDouble(symbol, SYMBOL_POINT);
   if(digits == 4 || digits == 0) return(point);
   return(point * 10.0);
  }

double CalculateLotSize(double slPips)
  {
   if(slPips <= 0) slPips = InpDefaultSLPips;

   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   if(balance <= 0) balance = InpAccountSize;

   double riskUSD    = balance * (InpRiskPercent / 100.0);
   double tickSize   = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_SIZE);
   double tickValue  = SymbolInfoDouble(_Symbol, SYMBOL_TRADE_TICK_VALUE);
   double point      = SymbolInfoDouble(_Symbol, SYMBOL_POINT);
   double pipSize    = GetPipSize(_Symbol);
   double minLot     = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MIN);
   double maxLot     = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_MAX);
   double stepLot    = SymbolInfoDouble(_Symbol, SYMBOL_VOLUME_STEP);
   int    lotDigits  = (int)SymbolInfoInteger(_Symbol, SYMBOL_VOLUME_DIGITS);

   if(tickSize <= 0 || tickValue <= 0 || point <= 0 || stepLot <= 0) return(minLot);

   double slInPoints = (slPips * pipSize) / point;
   double lossPerLot = (slInPoints * (point / tickSize)) * tickValue;
   if(lossPerLot <= 0) return(minLot);

   double rawLot     = riskUSD / lossPerLot;
   double roundedLot = MathFloor(rawLot / stepLot) * stepLot;
   if(roundedLot < minLot) roundedLot = minLot;
   if(roundedLot > maxLot) roundedLot = maxLot;

   return(NormalizeDouble(roundedLot, lotDigits));
  }

//+------------------------------------------------------------------+
//| Ejecucion de Ordenes (SL x1 / TP x R)                            |
//+------------------------------------------------------------------+
void ExecuteMarketOrder(ENUM_ORDER_TYPE orderType)
  {
   if(g_isDailyLocked)
     {
      Alert("[ILOF RISK] Operativa bloqueada: ", g_lockReason);
      return;
     }

   symInfo.RefreshRates();
   double pipSize = GetPipSize(_Symbol);
   int    digits  = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double lot     = CalculateLotSize(InpDefaultSLPips);
   double slDist  = InpDefaultSLPips * pipSize;
   double tpDist  = slDist * InpTPRatioR;

   double ask = symInfo.Ask();
   double bid = symInfo.Bid();
   double slPrice = 0.0, tpPrice = 0.0;
   bool   sent = false;

   if(orderType == ORDER_TYPE_BUY)
     {
      slPrice = NormalizeDouble(ask - slDist, digits);
      tpPrice = NormalizeDouble(ask + tpDist, digits);
      sent = trade.Buy(lot, _Symbol, ask, slPrice, tpPrice, InpComment);
     }
   else if(orderType == ORDER_TYPE_SELL)
     {
      slPrice = NormalizeDouble(bid + slDist, digits);
      tpPrice = NormalizeDouble(bid - tpDist, digits);
      sent = trade.Sell(lot, _Symbol, bid, slPrice, tpPrice, InpComment);
     }

   if(!sent)
      Alert("[ILOF] Orden no enviada: ", trade.ResultRetcodeDescription());

   CheckDailyLimits();
   UpdateHUD();
   ChartRedraw(0);
  }

//+------------------------------------------------------------------+
//| Gestion de Break-Even y Trailing (solo si se habilitan)          |
//+------------------------------------------------------------------+
void ManagePositionsSL()
  {
   if(!InpAutoBreakEven && !InpUseTrailingStop) return;

   double pipSize       = GetPipSize(_Symbol);
   int    digits        = (int)SymbolInfoInteger(_Symbol, SYMBOL_DIGITS);
   double beBuffer      = InpBEBufferPips * pipSize;
   double trailingDist  = InpTrailingDistancePips * pipSize;
   double trailingStep  = InpTrailingStepPips * pipSize;

   for(int i = PositionsTotal() - 1; i >= 0; i--)
     {
      if(!posInfo.SelectByIndex(i)) continue;
      if(posInfo.Symbol() != _Symbol) continue;
      if(posInfo.Magic() != InpMagicNumber) continue;

      ulong  ticket       = posInfo.Ticket();
      double openPrice    = posInfo.PriceOpen();
      double currentSL    = posInfo.StopLoss();
      double currentTP    = posInfo.TakeProfit();
      double currentPrice = posInfo.PriceCurrent();

      if(currentSL == 0) continue;
      double slDistance = MathAbs(openPrice - currentSL);

      // COMPRAS (BUY)
      if(posInfo.PositionType() == POSITION_TYPE_BUY)
        {
         if(InpAutoBreakEven && currentPrice >= (openPrice + (slDistance * InpBERatio)) && (currentSL < openPrice))
            trade.PositionModify(ticket, NormalizeDouble(openPrice + beBuffer, digits), currentTP);

         if(InpUseTrailingStop && (currentPrice - openPrice) > trailingDist)
           {
            double newSL = NormalizeDouble(currentPrice - trailingDist, digits);
            if(newSL > currentSL + trailingStep)
               trade.PositionModify(ticket, newSL, currentTP);
           }
        }
      // VENTAS (SELL)
      else if(posInfo.PositionType() == POSITION_TYPE_SELL)
        {
         if(InpAutoBreakEven && currentPrice <= (openPrice - (slDistance * InpBERatio)) && (currentSL > openPrice))
            trade.PositionModify(ticket, NormalizeDouble(openPrice - beBuffer, digits), currentTP);

         if(InpUseTrailingStop && (openPrice - currentPrice) > trailingDist)
           {
            double newSL = NormalizeDouble(currentPrice + trailingDist, digits);
            if(newSL < currentSL - trailingStep)
               trade.PositionModify(ticket, newSL, currentTP);
           }
        }
     }
  }

//+------------------------------------------------------------------+
//| Creacion UI / HUD Visual (botonera)                              |
//+------------------------------------------------------------------+
void CreateHUD()
  {
   DestroyHUD();
   color bgColor   = (InpTheme == THEME_DARK_PRO) ? C'18,22,30' : C'14,26,45';
   color hdrBg     = (InpTheme == THEME_DARK_PRO) ? C'28,36,52' : C'20,42,75';
   color borderCol = (InpTheme == THEME_DARK_PRO) ? C'45,55,75' : C'35,70,120';

   CreateRectLabel(HUD_PREFIX + "BG", InpHUD_X, InpHUD_Y, InpHUD_Width, InpHUD_Height, bgColor, borderCol);
   CreateRectLabel(HUD_PREFIX + "HDR", InpHUD_X + 2, InpHUD_Y + 2, InpHUD_Width - 4, 30, hdrBg, hdrBg);
   CreateLabel(HUD_PREFIX + "TITLE", InpHUD_X + 10, InpHUD_Y + 7, "ILOF EXECUTIVE PRO", clrAqua, 10, true);

   string labels[] = {"Estado Cuenta:", "Equity / Balance:", "Daily Drawdown:", "Max Daily Limit ($):", "Lote Calc (0.5%):", "Trades Hoy / Max:"};
   string keys[]   = {"VAL_STATUS", "VAL_EQ_BAL", "VAL_DD", "VAL_MAX_DD", "VAL_LOT", "VAL_TRADES"};

   int yOffset = InpHUD_Y + 40;
   for(int i = 0; i < 6; i++)
     {
      CreateLabel(HUD_PREFIX + "LBL_" + IntegerToString(i), InpHUD_X + 14, yOffset, labels[i], clrLightGray, 9, false);
      CreateLabel(HUD_PREFIX + keys[i], InpHUD_X + 160, yOffset, "--", clrYellow, 9, true);
      yOffset += 20;
     }

   yOffset += 10;
   CreateButton(HUD_PREFIX + "BTN_BUY",  InpHUD_X + 14, yOffset, 100, 25, "BUY",  C'0,120,60',   clrWhite);
   CreateButton(HUD_PREFIX + "BTN_SELL", InpHUD_X + 122, yOffset, 100, 25, "SELL", C'160,30,30', clrWhite);
   CreateButton(HUD_PREFIX + "BTN_RESET",InpHUD_X + 230, yOffset, 100, 25, "RESET",C'180,120,0', clrWhite);

   g_hudInitialized = true;
  }

void UpdateHUD()
  {
   if(!g_hudInitialized) return;

   double equity  = AccountInfoDouble(ACCOUNT_EQUITY);
   double balance = AccountInfoDouble(ACCOUNT_BALANCE);
   double dailyPL = equity - g_initialDailyBalance;
   double ddUSD   = (dailyPL < 0) ? -dailyPL : 0.0;
   double ddPct   = (g_initialDailyBalance > 0) ? (ddUSD / g_initialDailyBalance) * 100.0 : 0.0;
   double lot     = CalculateLotSize(InpDefaultSLPips);

   ObjectSetString(0, HUD_PREFIX + "VAL_STATUS", OBJPROP_TEXT,  g_isDailyLocked ? "BLOQUEADO" : "OPERATIVO");
   ObjectSetInteger(0, HUD_PREFIX + "VAL_STATUS", OBJPROP_COLOR, g_isDailyLocked ? clrRed : clrLime);

   ObjectSetString(0, HUD_PREFIX + "VAL_EQ_BAL", OBJPROP_TEXT, StringFormat("$%.2f / $%.2f", equity, balance));
   ObjectSetString(0, HUD_PREFIX + "VAL_DD", OBJPROP_TEXT, StringFormat("$%.2f (%.2f%%)", ddUSD, ddPct));
   ObjectSetString(0, HUD_PREFIX + "VAL_MAX_DD", OBJPROP_TEXT, StringFormat("$%.2f", InpMaxDailyLossUSD));
   ObjectSetString(0, HUD_PREFIX + "VAL_LOT", OBJPROP_TEXT, StringFormat("%.2f Lotes (SL%.0f/TP%.0f)", lot, InpDefaultSLPips, InpDefaultSLPips * InpTPRatioR));
   ObjectSetString(0, HUD_PREFIX + "VAL_TRADES", OBJPROP_TEXT, StringFormat("%d / %d", g_dailyTradesCount, InpMaxDailyTrades));
  }

void DestroyHUD()
  {
   ObjectsDeleteAll(0, HUD_PREFIX);
   g_hudInitialized = false;
  }

//--- HELPER UTILITIES
void CreateRectLabel(string name, int x, int y, int w, int h, color bgCol, color borderCol)
  {
   if(ObjectFind(0, name) < 0) ObjectCreate(0, name, OBJ_RECTANGLE_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, bgCol);
   ObjectSetInteger(0, name, OBJPROP_BORDER_TYPE, BORDER_FLAT);
   ObjectSetInteger(0, name, OBJPROP_COLOR, borderCol);
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
   ObjectSetInteger(0, name, OBJPROP_BACK, false);
  }

void CreateLabel(string name, int x, int y, string text, color col, int fontSize=9, bool isBold=false)
  {
   if(ObjectFind(0, name) < 0) ObjectCreate(0, name, OBJ_LABEL, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_COLOR, col);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, fontSize);
   ObjectSetString(0, name, OBJPROP_FONT, isBold ? "Arial Bold" : "Arial");
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }

void CreateButton(string name, int x, int y, int w, int h, string text, color bgCol, color txtCol)
  {
   if(ObjectFind(0, name) < 0) ObjectCreate(0, name, OBJ_BUTTON, 0, 0, 0);
   ObjectSetInteger(0, name, OBJPROP_CORNER, CORNER_LEFT_UPPER);
   ObjectSetInteger(0, name, OBJPROP_XDISTANCE, x);
   ObjectSetInteger(0, name, OBJPROP_YDISTANCE, y);
   ObjectSetInteger(0, name, OBJPROP_XSIZE, w);
   ObjectSetInteger(0, name, OBJPROP_YSIZE, h);
   ObjectSetString(0, name, OBJPROP_TEXT, text);
   ObjectSetInteger(0, name, OBJPROP_BGCOLOR, bgCol);
   ObjectSetInteger(0, name, OBJPROP_COLOR, txtCol);
   ObjectSetInteger(0, name, OBJPROP_FONTSIZE, 8);
   ObjectSetString(0, name, OBJPROP_FONT, "Arial Bold");
   ObjectSetInteger(0, name, OBJPROP_SELECTABLE, false);
  }