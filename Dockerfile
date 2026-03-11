# Stage 1: Build the React frontend
FROM node:22-alpine AS frontend-builder
WORKDIR /app/web

# Install dependencies and build
COPY web/package.json ./
RUN npm install --legacy-peer-deps
COPY web/ ./
RUN npm run build

# Stage 2: Build the Go backend
FROM golang:1.25-alpine AS backend-builder
WORKDIR /app

# Download Go modules
COPY go.mod go.sum ./
RUN go mod download

# Copy the source code
COPY cmd/ cmd/
COPY api/ api/
COPY core/ core/
COPY models/ models/
COPY proto/ proto/
COPY rules/ rules/
COPY web/ web/

# Build the Go binary
RUN CGO_ENABLED=0 GOOS=linux go build -o /server ./cmd/server

# Stage 3: Final Production Image
FROM alpine:latest
WORKDIR /app

# Install root certificates in case we need to make HTTPS requests
RUN apk --no-cache add ca-certificates tzdata

# Copy the compiled Go binary
COPY --from=backend-builder /server /app/server

# Copy the built React assets
# We will place them in /app/web/dist since that's where the Go server expects them
COPY --from=frontend-builder /app/web/dist /app/web/dist

# Expose the API port
EXPOSE 8080

# Command to run the executable
CMD ["/app/server"]
