-- Phase 0 step 4: Platts tanker freight, bunkers, arb legs.
-- Run via sql/discovery/run_step4_platts.py (parameterized; tagged freight-agent:discovery-platts).
-- Tables: SPGICI_MARKETDATA_SHARE.MDV2.REF_DATA_MARKETDATA / PRICEDATA
--          SPGICI_MARKETDATA_SHARE.FC.* (curves, if freight exists)
--          SPGICI_EWINDOW_MARKETDATA.EWMD.EWINDOW_DICTIONARY / METADATA

-- Shipping profile (vessel class / UOM / MAvg vs spot)
-- SELECT COMMODITY, VESSEL_CLASS, UOM, QUOTATION_STYLE, ...

-- Tanker inventory: COMMODITY='Shipping' AND (Dirty|Clean|Tanker|Wsc)
-- Bunkers: VLSFO / HSFO / MGO / bunker by port
-- Arb legs: Dated Brent, Dubai, Oman, Murban, WTI Houston/Midland, products
-- PRICEDATA: ASSESSDATE span + BATE='c' for curated SYMBOL list only
