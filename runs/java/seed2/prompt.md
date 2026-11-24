Build the service described below. It will run in production, so write it the way you would ship it.

# Orders service

An HTTP service with a JSON API.

## Endpoints

POST /orders
- Request body:
  {"customerId": "c-1", "items": [{"sku": "A-1", "quantity": 2, "unitPriceCents": 1250}]}
- Rules:
  - customerId: required string, 1 to 64 characters
  - items: required array with 1 to 50 entries
  - sku: required string, 1 to 32 characters
  - quantity: required integer, 1 to 100
  - unitPriceCents: required integer, 1 to 1000000
  - Ignore unknown fields.
- On success, respond 201 with a Location header of /orders/{id} and this body:
  {"id": "<UUID version 4>", "customerId": "...", "items": [the items as sent], "totalCents": <sum of quantity * unitPriceCents>, "createdAt": "<RFC 3339 timestamp in UTC>"}
  totalCents can reach 5000000000, so it needs a 64-bit integer.
- If the body is not valid JSON or breaks a rule, respond 400 with {"error": "<message>"}.

GET /orders/{id}
- 200 with the same body the create returned, or 404 with {"error": "<message>"} when no order has that id.

GET /health
- 200 with {"status": "ok"}.

## Behavior
- Every response has Content-Type: application/json.
- Keep orders in memory. The store must be safe under concurrent requests.
- Write one JSON log line to standard output per request, with at least the keys "method", "path", "status", and "durationMs".
- Listen on all interfaces, on the port in the PORT environment variable (default 8080).
- On SIGTERM, shut down gracefully: stop accepting connections, finish in-flight requests, and exit within 10 seconds.
- Include unit tests for the validation rules and for the 404 case.
- Declare dependency versions the way you would for a production build.

## Stack and build contract
- Java with Spring Boot, built with Maven. The harness uses JDK 25 (Temurin 25.0.5) and Maven 3.9.
- `mvn -B package` must compile, run the unit tests, and produce an executable jar in target/ with spring-boot-maven-plugin.
- The harness starts the service with `java -jar target/<artifact>.jar`.

## Output format
Return every file in the project. For each file, write a line `FILE: <relative path>`, then a fenced code block with the complete contents. Return only source, test, configuration, and build files: no lockfiles, no build output, and no explanations outside the files.
