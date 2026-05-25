use std::fs::File;
use std::path::Path;
use std::sync::Arc;

use anyhow::Result;
use arrow::array::{Float64Array, Int64Array, RecordBatch, StringArray};
use arrow::compute::concat_batches;
use arrow::datatypes::{DataType, Field, Schema, SchemaRef};
use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
use parquet::arrow::arrow_writer::ArrowWriter;
use parquet::basic::Compression;
use parquet::file::properties::WriterProperties;

use crate::records::{BookLevel, FundingRecord, FuturesOrderBookRecord, SpotOrderBookRecord};

#[derive(Debug, Clone)]
pub enum CollectorRecord {
    Spot(SpotOrderBookRecord),
    Futures(FuturesOrderBookRecord),
    Funding(FundingRecord),
}

pub fn write_spot_records(path: &Path, new_records: &[SpotOrderBookRecord]) -> Result<()> {
    append_batch(path, spot_schema(), spot_batch(spot_schema(), new_records)?)
}

pub fn write_futures_records(path: &Path, new_records: &[FuturesOrderBookRecord]) -> Result<()> {
    append_batch(
        path,
        futures_schema(),
        futures_batch(futures_schema(), new_records)?,
    )
}

pub fn write_funding_records(path: &Path, new_records: &[FundingRecord]) -> Result<()> {
    append_batch(
        path,
        funding_schema(),
        funding_batch(funding_schema(), new_records)?,
    )
}

fn append_batch(path: &Path, schema: SchemaRef, new_batch: RecordBatch) -> Result<()> {
    let batch = if path.exists() {
        let mut batches = read_batches(path)?;
        batches.push(new_batch);
        concat_batches(&schema, &batches)?
    } else {
        new_batch
    };
    write_record_batch(path, schema, batch)
}

fn write_record_batch(path: &Path, schema: SchemaRef, batch: RecordBatch) -> Result<()> {
    if let Some(parent) = path.parent() {
        std::fs::create_dir_all(parent)?;
        ensure_disk_space(parent)?;
    }

    let tmp_path = path.with_extension("parquet.tmp");
    let file = File::create(&tmp_path)?;
    let props = WriterProperties::builder()
        .set_compression(Compression::SNAPPY)
        .build();
    let mut writer = ArrowWriter::try_new(file, schema, Some(props))?;
    writer.write(&batch)?;
    writer.close()?;

    let tmp_file = File::open(&tmp_path)?;
    ParquetRecordBatchReaderBuilder::try_new(tmp_file)?;
    std::fs::rename(&tmp_path, path)?;

    Ok(())
}

fn ensure_disk_space(path: &Path) -> Result<()> {
    let free = fs2::available_space(path)?;
    let min_free = 1024_u64 * 1024 * 1024;
    if free < min_free {
        anyhow::bail!("disk space below 1 GiB at {}", path.display());
    }
    Ok(())
}

fn read_batches(path: &Path) -> Result<Vec<RecordBatch>> {
    let file = File::open(path)?;
    let reader = ParquetRecordBatchReaderBuilder::try_new(file)?.build()?;
    reader.collect::<Result<Vec<_>, _>>().map_err(Into::into)
}

fn spot_batch(schema: SchemaRef, records: &[SpotOrderBookRecord]) -> Result<RecordBatch> {
    let mut arrays: Vec<Arc<dyn arrow::array::Array>> = vec![
        Arc::new(Int64Array::from_iter_values(
            records.iter().map(|r| r.timestamp),
        )),
        Arc::new(Int64Array::from_iter_values(
            records.iter().map(|r| r.local_timestamp),
        )),
        Arc::new(StringArray::from_iter_values(
            records.iter().map(|r| r.symbol.as_str()),
        )),
        Arc::new(StringArray::from_iter_values(
            records.iter().map(|r| r.market_type.as_str()),
        )),
        Arc::new(Int64Array::from_iter_values(
            records.iter().map(|r| r.first_update_id),
        )),
    ];

    push_level_arrays(&mut arrays, records, |record| &record.bids);
    push_level_arrays(&mut arrays, records, |record| &record.asks);

    arrays.push(Arc::new(Int64Array::from_iter_values(
        records.iter().map(|r| r.last_update_id),
    )));

    Ok(RecordBatch::try_new(schema, arrays)?)
}

fn futures_batch(schema: SchemaRef, records: &[FuturesOrderBookRecord]) -> Result<RecordBatch> {
    let mut arrays: Vec<Arc<dyn arrow::array::Array>> = vec![
        Arc::new(Int64Array::from_iter_values(
            records.iter().map(|r| r.timestamp),
        )),
        Arc::new(Int64Array::from_iter_values(
            records.iter().map(|r| r.local_timestamp),
        )),
        Arc::new(StringArray::from_iter_values(
            records.iter().map(|r| r.symbol.as_str()),
        )),
        Arc::new(StringArray::from_iter_values(
            records.iter().map(|r| r.market_type.as_str()),
        )),
        Arc::new(Int64Array::from_iter_values(
            records.iter().map(|r| r.transaction_time),
        )),
        Arc::new(Int64Array::from_iter_values(
            records.iter().map(|r| r.first_update_id),
        )),
        Arc::new(Int64Array::from_iter_values(
            records.iter().map(|r| r.prev_update_id),
        )),
    ];

    push_futures_level_arrays(&mut arrays, records, |record| &record.bids);
    push_futures_level_arrays(&mut arrays, records, |record| &record.asks);

    arrays.push(Arc::new(Int64Array::from_iter_values(
        records.iter().map(|r| r.last_update_id),
    )));

    Ok(RecordBatch::try_new(schema, arrays)?)
}

fn funding_batch(schema: SchemaRef, records: &[FundingRecord]) -> Result<RecordBatch> {
    let arrays: Vec<Arc<dyn arrow::array::Array>> = vec![
        Arc::new(Int64Array::from_iter_values(
            records.iter().map(|r| r.timestamp),
        )),
        Arc::new(Int64Array::from_iter_values(
            records.iter().map(|r| r.local_timestamp),
        )),
        Arc::new(StringArray::from_iter_values(
            records.iter().map(|r| r.symbol.as_str()),
        )),
        Arc::new(Float64Array::from_iter_values(
            records.iter().map(|r| r.funding_rate),
        )),
        Arc::new(Float64Array::from_iter_values(
            records.iter().map(|r| r.mark_price),
        )),
        Arc::new(Float64Array::from_iter_values(
            records.iter().map(|r| r.index_price),
        )),
        Arc::new(Int64Array::from_iter_values(
            records.iter().map(|r| r.next_funding_time),
        )),
        Arc::new(Float64Array::from_iter_values(
            records.iter().map(|r| r.open_interest),
        )),
        Arc::new(Float64Array::from_iter_values(
            records.iter().map(|r| r.volume_24h),
        )),
    ];

    Ok(RecordBatch::try_new(schema, arrays)?)
}

fn push_level_arrays<F>(
    arrays: &mut Vec<Arc<dyn arrow::array::Array>>,
    records: &[SpotOrderBookRecord],
    levels: F,
) where
    F: Fn(&SpotOrderBookRecord) -> &[BookLevel],
{
    for idx in 0..20 {
        arrays.push(Arc::new(Float64Array::from_iter_values(
            records.iter().map(|record| {
                levels(record)
                    .get(idx)
                    .map(|level| level.price)
                    .unwrap_or_default()
            }),
        )));
        arrays.push(Arc::new(Float64Array::from_iter_values(
            records.iter().map(|record| {
                levels(record)
                    .get(idx)
                    .map(|level| level.qty)
                    .unwrap_or_default()
            }),
        )));
    }
}

fn push_futures_level_arrays<F>(
    arrays: &mut Vec<Arc<dyn arrow::array::Array>>,
    records: &[FuturesOrderBookRecord],
    levels: F,
) where
    F: Fn(&FuturesOrderBookRecord) -> &[BookLevel],
{
    for idx in 0..20 {
        arrays.push(Arc::new(Float64Array::from_iter_values(
            records.iter().map(|record| {
                levels(record)
                    .get(idx)
                    .map(|level| level.price)
                    .unwrap_or_default()
            }),
        )));
        arrays.push(Arc::new(Float64Array::from_iter_values(
            records.iter().map(|record| {
                levels(record)
                    .get(idx)
                    .map(|level| level.qty)
                    .unwrap_or_default()
            }),
        )));
    }
}

fn spot_schema() -> SchemaRef {
    let mut fields = vec![
        Field::new("timestamp", DataType::Int64, false),
        Field::new("local_timestamp", DataType::Int64, false),
        Field::new("symbol", DataType::Utf8, false),
        Field::new("market_type", DataType::Utf8, false),
        Field::new("first_update_id", DataType::Int64, false),
    ];
    for side in ["bid", "ask"] {
        for level in 1..=20 {
            fields.push(Field::new(
                format!("{side}{level}_price"),
                DataType::Float64,
                false,
            ));
            fields.push(Field::new(
                format!("{side}{level}_qty"),
                DataType::Float64,
                false,
            ));
        }
    }
    fields.push(Field::new("last_update_id", DataType::Int64, false));
    Arc::new(Schema::new(fields))
}

fn futures_schema() -> SchemaRef {
    let mut fields = vec![
        Field::new("timestamp", DataType::Int64, false),
        Field::new("local_timestamp", DataType::Int64, false),
        Field::new("symbol", DataType::Utf8, false),
        Field::new("market_type", DataType::Utf8, false),
        Field::new("transaction_time", DataType::Int64, false),
        Field::new("first_update_id", DataType::Int64, false),
        Field::new("prev_update_id", DataType::Int64, false),
    ];
    for side in ["bid", "ask"] {
        for level in 1..=20 {
            fields.push(Field::new(
                format!("{side}{level}_price"),
                DataType::Float64,
                false,
            ));
            fields.push(Field::new(
                format!("{side}{level}_qty"),
                DataType::Float64,
                false,
            ));
        }
    }
    fields.push(Field::new("last_update_id", DataType::Int64, false));
    Arc::new(Schema::new(fields))
}

fn funding_schema() -> SchemaRef {
    Arc::new(Schema::new(vec![
        Field::new("timestamp", DataType::Int64, false),
        Field::new("local_timestamp", DataType::Int64, false),
        Field::new("symbol", DataType::Utf8, false),
        Field::new("funding_rate", DataType::Float64, false),
        Field::new("mark_price", DataType::Float64, false),
        Field::new("index_price", DataType::Float64, false),
        Field::new("next_funding_time", DataType::Int64, false),
        Field::new("open_interest", DataType::Float64, false),
        Field::new("volume_24h", DataType::Float64, false),
    ]))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::records::{BookLevel, SpotOrderBookRecord};
    use parquet::arrow::arrow_reader::ParquetRecordBatchReaderBuilder;
    use std::fs::File;

    #[test]
    fn rewrite_preserves_existing_spot_rows_and_appends_new_rows() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("spot_BTCUSDT_2026052516.parquet");
        let first = spot_record(100, 1.0);
        let second = spot_record(200, 2.0);

        write_spot_records(&path, &[first.clone()]).unwrap();
        write_spot_records(&path, &[second.clone()]).unwrap();

        let file = File::open(&path).unwrap();
        let builder = ParquetRecordBatchReaderBuilder::try_new(file).unwrap();
        let row_count = builder.metadata().file_metadata().num_rows();

        assert_eq!(row_count, 2);
    }

    fn spot_record(last_update_id: i64, bid_price: f64) -> SpotOrderBookRecord {
        SpotOrderBookRecord {
            timestamp: 1_700_000_000_000 + last_update_id,
            local_timestamp: 1_700_000_000_100 + last_update_id,
            symbol: "BTCUSDT".to_string(),
            market_type: "spot".to_string(),
            first_update_id: last_update_id,
            bids: vec![BookLevel {
                price: bid_price,
                qty: 1.0,
            }],
            asks: vec![BookLevel {
                price: bid_price + 1.0,
                qty: 2.0,
            }],
            last_update_id,
        }
    }
}
