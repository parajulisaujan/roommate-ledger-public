FROM maven:3.9.11-eclipse-temurin-21 AS build
WORKDIR /app
COPY pom.xml .
RUN mvn -B -ntp dependency:go-offline
COPY src ./src
RUN mvn -B -ntp package

FROM eclipse-temurin:21-jre-alpine
RUN addgroup -S ledger && adduser -S ledger -G ledger
WORKDIR /app
COPY --from=build /app/target/roommate-ledger-1.0.0.jar app.jar
USER ledger
EXPOSE 8080
ENTRYPOINT ["java","-jar","app.jar"]
