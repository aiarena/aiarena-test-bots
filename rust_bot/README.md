This Rust bot is based on the worker rush example of https://github.com/UltraMachine/rust-sc2

Compile it with:
```
docker build -t rust_bot .
docker create --name rust_bot_temp rust_bot
docker cp rust_bot_temp:/app/target/release/rust_bot ./rust_bot
docker rm rust_bot_temp
```
