docker run \
    -p 9000:9000 -p 9009:9009 -p 8812:8812 -p 9003:9003 \
    -v "./quest_data:/var/lib/questdb"  \
    questdb/questdb:8.1.4 