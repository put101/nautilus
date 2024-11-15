# nautilus
 Nautilus quant stuff.


# local packages
No module named strategies
`pip install -e strategies `

2024-11-14T22:48:16.325715001Z [ERROR] BACKTESTER-001.BacktestNode: Error running backtest: No module named 'put101'
`pip install -e strategies put101`


# influxdb

```sh
(nautilus-py3.11) (base) ➜  docker git:(main) ✗ docker run -p 8080:8086 \
-v $PWD/config:/etc/influxdb2 \
-v $PWD/data:/var/lib/influxdb2 \
--net influxdb_net \ 
--name influxdb \
-d \
> influxdb
```
