# SAMAA TV News Scraper API

**Registration:** FA23-BAI-010  
**News Source:** SAMAA TV

## Build the Docker Image
docker build -t ashesdock/samaa-scraper:latest .

## Run the Container
docker run -d -p 7000:7000 ashesdock/samaa-scraper:latest

## Test the API
curl "http://localhost:7000/get?keyword=imran+khan"

## Expected Response
{
  "registration": "FA23-BAI-010",
  "newssource": "SAMAA TV",
  "keyword": "imran khan",
  "url": "https://www.samaa.tv/...",
  "summary": "..."
}