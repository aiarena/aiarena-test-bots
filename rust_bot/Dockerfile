# Use Debian Bookworm as the base image
FROM debian:bookworm

# Install Rust and build dependencies
RUN apt-get update && apt-get install -y \
    curl \
    build-essential \
    pkg-config \
    libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Rust using rustup with a specific nightly version (before strict custom_inner_attributes enforcement)
RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --default-toolchain nightly-2024-12-01
ENV PATH="/root/.cargo/bin:${PATH}"

# Set the working directory
WORKDIR /app

# Copy Cargo.toml and Cargo.lock (if exists)
COPY Cargo.toml ./

# Copy the source code
COPY bot.rs ./

# Build the Rust project in release mode
RUN cargo build --release
