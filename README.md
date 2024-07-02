# nautilus
 Nautilus quant stuff.

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
