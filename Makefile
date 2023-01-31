# General release info
BUILD_DATE        := $(shell date -u +'%Y-%m-%dT%H:%M:%SZ')
BUILD_VERSION     := 0.3.0
DOCKER_ACCOUNT    := boeboe
CONTAINER_NAME    := demo-app-abc
IMAGE_DESCRIPTION := Python demo app-abc
IMAGE_NAME        := demo-app-abc
APP_VERSION       := 0.3.0
REPO_URL          := https://github.com/boeboe/python-demo-app-abc
URL               := https://github.com/boeboe/python-demo-app-abc

BUILD_ARGS := --build-arg BUILD_DATE="${BUILD_DATE}" \
							--build-arg BUILD_VERSION="${BUILD_VERSION}" \
							--build-arg DOCKER_ACCOUNT="${DOCKER_ACCOUNT}" \
							--build-arg IMAGE_DESCRIPTION="${IMAGE_DESCRIPTION}" \
							--build-arg IMAGE_NAME="${IMAGE_NAME}" \
							--build-arg APP_VERSION="${APP_VERSION}" \
							--build-arg REPO_URL="${REPO_URL}" \
							--build-arg URL="${URL}" \
							--build-arg REPO_URL="${REPO_URL}"

# HELP
# This will output the help for each task
# thanks to https://marmelab.com/blog/2016/02/29/auto-documented-makefile.html
.PHONY: help

help: ## This help
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z0-9_-]+:.*?## / {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}' $(MAKEFILE_LIST)

.DEFAULT_GOAL := help

build: ## Build the container
	docker build ${BUILD_ARGS} -t $(DOCKER_ACCOUNT)/${IMAGE_NAME} .

build-nc: ## Build the container without cache
	docker build ${BUILD_ARGS} --no-cache -t $(DOCKER_ACCOUNT)/${IMAGE_NAME} .

run: ## Run docker compose environment
	docker-compose up -d

stop: ## Stop and remove docker compose environment
	docker-compose down -v

test-curl: ## Send curl traffic
	@echo '# Generating random requestid, traceid and spanid'
	@echo 'requestid=`echo $$RANDOM | md5sum | head -c 32` ;'
	@echo 'traceid=`echo $$RANDOM | md5sum | head -c 32` ;'
	@echo 'spanid=`echo $$RANDOM | md5sum | head -c 16` ;'
	@echo ''
	@echo '# Generate traffic command using those random ids'
	@echo 'curl http://127.0.0.1:5000/ -H "x-b3-sampled: 1" -H "x-request-id: $$requestid" -H "x-b3-traceid: $$traceid" -H "x-b3-spanid: $$spanid" ;'

publish: ## Tag and publish container
	docker tag $(DOCKER_ACCOUNT)/${IMAGE_NAME} $(DOCKER_ACCOUNT)/${IMAGE_NAME}:${BUILD_VERSION}
	docker push $(DOCKER_ACCOUNT)/${IMAGE_NAME}:${BUILD_VERSION}

release: build publish ## Make a full release
	@echo "Check released tags on https://hub.docker.com/r/$(DOCKER_ACCOUNT)/${IMAGE_NAME}/tags"

deploy-app-abc: ## Deploy app-abc in kubernetes
	kubectl apply -f kubernetes/

undeploy-app-abc: ## Undeploy app-abc from kubernetes
	kubectl delete -f kubernetes/
