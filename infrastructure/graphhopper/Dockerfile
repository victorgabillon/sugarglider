FROM eclipse-temurin:25-jre-jammy

ARG GRAPHHOPPER_VERSION=11.0
RUN apt-get update \
    && apt-get install --yes --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && curl --fail --location --retry 3 \
       "https://repo1.maven.org/maven2/com/graphhopper/graphhopper-web/${GRAPHHOPPER_VERSION}/graphhopper-web-${GRAPHHOPPER_VERSION}.jar" \
       --output /opt/graphhopper-web.jar

COPY config.yml /opt/graphhopper/config.yml
COPY custom_models /opt/graphhopper/custom_models
COPY entrypoint.sh /usr/local/bin/graphhopper-entrypoint
RUN { printf '%s\n' "${GRAPHHOPPER_VERSION}"; \
      cat /opt/graphhopper/config.yml /opt/graphhopper/custom_models/*.json; } \
      | sha256sum | cut -d ' ' -f 1 > /opt/graphhopper/import-fingerprint \
    && chmod +x /usr/local/bin/graphhopper-entrypoint

WORKDIR /opt/graphhopper
EXPOSE 8989
ENTRYPOINT ["graphhopper-entrypoint"]
