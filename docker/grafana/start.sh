# start grafana
docker run -d -p 3000:3000 --name=grafana --network main_network  --volume grafana-storage:/var/lib/grafana   grafana/grafana-enterprise
