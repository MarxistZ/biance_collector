#[derive(Debug, Clone, PartialEq)]
pub struct BookLevel {
    pub price: f64,
    pub qty: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct SpotOrderBookRecord {
    pub timestamp: i64,
    pub local_timestamp: i64,
    pub symbol: String,
    pub market_type: String,
    pub first_update_id: i64,
    pub bids: Vec<BookLevel>,
    pub asks: Vec<BookLevel>,
    pub last_update_id: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FuturesOrderBookRecord {
    pub timestamp: i64,
    pub local_timestamp: i64,
    pub symbol: String,
    pub market_type: String,
    pub transaction_time: i64,
    pub first_update_id: i64,
    pub prev_update_id: i64,
    pub bids: Vec<BookLevel>,
    pub asks: Vec<BookLevel>,
    pub last_update_id: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FundingRecord {
    pub timestamp: i64,
    pub local_timestamp: i64,
    pub symbol: String,
    pub funding_rate: f64,
    pub mark_price: f64,
    pub index_price: f64,
    pub next_funding_time: i64,
    pub open_interest: f64,
    pub volume_24h: f64,
}
