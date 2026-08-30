#!/usr/bin/env bash
set -Eeuo pipefail

fail() {
  echo "SIGESC_DEPLOY_ERROR=$1" >&2
  exit 1
}

require_safe_token() {
  local label="$1" value="$2"
  [[ "$value" =~ ^[A-Za-z0-9._-]+$ ]] || fail "${label}_INVALID"
}

find_service_container() {
  local project="$1" service="$2"
  local rows
  rows="$(docker ps -a \
    --filter "label=com.docker.compose.project=${project}" \
    --filter "label=com.docker.compose.service=${service}" \
    --format '{{.Names}}')"
  [ "$(printf '%s\n' "$rows" | sed '/^$/d' | wc -l | tr -d ' ')" = "1" ] \
    || fail "SERVICE_CONTAINER_CARDINALITY_${service}"
  printf '%s\n' "$rows"
}

wait_service_healthy() {
  local project="$1" service="$2" timeout_seconds="${3:-300}"
  local deadline=$((SECONDS + timeout_seconds))
  while [ "$SECONDS" -lt "$deadline" ]; do
    local cname state health
    cname="$(find_service_container "$project" "$service")"
    state="$(docker inspect -f '{{.State.Status}}' "$cname")"
    health="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$cname")"
    if [ "$state" = "running" ] && [ "$health" = "healthy" ]; then
      printf '%s\n' "$cname"
      return 0
    fi
    sleep 5
  done
  return 1
}

image_revision_for_container() {
  local cname="$1" image_id
  image_id="$(docker inspect -f '{{.Image}}' "$cname")"
  docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$image_id" 2>/dev/null || true
}

write_shell_kv() {
  local file="$1" key="$2" value="$3"
  printf '%s=%q\n' "$key" "$value" >> "$file"
}

restore_old_images_and_runtime() {
  local project="$1" compose_path="$2" override_path="$3"
  local old_backend_id="$4" old_backend_ref="$5" old_frontend_id="$6" old_frontend_ref="$7"
  local backend_container frontend_container

  docker image tag "$old_backend_id" "$old_backend_ref" || return 1
  docker image tag "$old_frontend_id" "$old_frontend_ref" || return 1

  docker compose -p "$project" -f "$compose_path" -f "$override_path" \
    up -d --no-deps --no-build --force-recreate backend || return 1
  backend_container="$(wait_service_healthy "$project" backend 300)" || return 1
  [ "$(docker inspect -f '{{.Image}}' "$backend_container")" = "$old_backend_id" ] || return 1

  docker compose -p "$project" -f "$compose_path" -f "$override_path" \
    up -d --no-deps --no-build --force-recreate frontend || return 1
  frontend_container="$(wait_service_healthy "$project" frontend 180)" || return 1
  [ "$(docker inspect -f '{{.Image}}' "$frontend_container")" = "$old_frontend_id" ] || return 1

  return 0
}

mode="${1:-}"
shift || true

case "$mode" in
  deploy)
    [ "$#" -eq 6 ] || fail "DEPLOY_ARGUMENT_COUNT"
    project="$1"
    workdir="$2"
    compose_path="$3"
    release_dir="$4"
    target_sha="$5"
    run_id="$6"

    require_safe_token COMPOSE_PROJECT "$project"
    require_safe_token RUN_ID "$run_id"
    [[ "$target_sha" =~ ^[0-9a-f]{40}$ ]] || fail "TARGET_SHA_INVALID"
    [ -d "$workdir" ] || fail "WORKDIR_NOT_FOUND"
    [ -f "$compose_path" ] || fail "COMPOSE_NOT_FOUND"
    [ -d "$release_dir/backend" ] || fail "BACKEND_RELEASE_NOT_FOUND"
    [ -d "$release_dir/frontend" ] || fail "FRONTEND_RELEASE_NOT_FOUND"

    case "$workdir" in
      /data/coolify/applications/*) ;;
      *) fail "WORKDIR_OUTSIDE_COOLIFY" ;;
    esac
    case "$release_dir" in
      "$workdir"/.github-deploy/releases/*) ;;
      *) fail "RELEASE_OUTSIDE_GITHUB_DEPLOY_ROOT" ;;
    esac

    mongo_container="$(find_service_container "$project" mongo)"
    backend_container="$(find_service_container "$project" backend)"
    frontend_container="$(find_service_container "$project" frontend)"

    [ "$(docker inspect -f '{{.State.Health.Status}}' "$mongo_container")" = "healthy" ] \
      || fail "MONGO_NOT_HEALTHY_BEFORE_DEPLOY"

    mongo_container_id_before="$(docker inspect -f '{{.Id}}' "$mongo_container")"
    old_backend_image_id="$(docker inspect -f '{{.Image}}' "$backend_container")"
    old_frontend_image_id="$(docker inspect -f '{{.Image}}' "$frontend_container")"
    old_backend_image_ref="$(docker inspect -f '{{.Config.Image}}' "$backend_container")"
    old_frontend_image_ref="$(docker inspect -f '{{.Config.Image}}' "$frontend_container")"

    [ -n "$old_backend_image_id" ] && [ -n "$old_frontend_image_id" ] \
      || fail "OLD_IMAGE_ID_MISSING"
    [ -n "$old_backend_image_ref" ] && [ -n "$old_frontend_image_ref" ] \
      || fail "OLD_IMAGE_REF_MISSING"

    deploy_root="$workdir/.github-deploy"
    override_dir="$deploy_root/overrides"
    receipt_dir="$deploy_root/receipts"
    mkdir -p "$override_dir" "$receipt_dir"

    override_path="$override_dir/${target_sha}-${run_id}.yml"
    receipt_path="$receipt_dir/${target_sha}-${run_id}.env"

    cat > "$override_path" <<EOF
services:
  backend:
    build:
      context: ${release_dir}/backend
      dockerfile: Dockerfile
      args:
        SIGESC_GIT_SHA: ${target_sha}
  frontend:
    build:
      context: ${release_dir}/frontend
      dockerfile: Dockerfile
      args:
        SIGESC_GIT_SHA: ${target_sha}
EOF

    : > "$receipt_path"
    write_shell_kv "$receipt_path" RECEIPT_SCHEMA SIGESC_GITHUB_ONLY_DEPLOY_V1
    write_shell_kv "$receipt_path" PROJECT "$project"
    write_shell_kv "$receipt_path" WORKDIR "$workdir"
    write_shell_kv "$receipt_path" COMPOSE_PATH "$compose_path"
    write_shell_kv "$receipt_path" OVERRIDE_PATH "$override_path"
    write_shell_kv "$receipt_path" RELEASE_DIR "$release_dir"
    write_shell_kv "$receipt_path" TARGET_SHA "$target_sha"
    write_shell_kv "$receipt_path" RUN_ID "$run_id"
    write_shell_kv "$receipt_path" MONGO_CONTAINER_ID_BEFORE "$mongo_container_id_before"
    write_shell_kv "$receipt_path" OLD_BACKEND_IMAGE_ID "$old_backend_image_id"
    write_shell_kv "$receipt_path" OLD_FRONTEND_IMAGE_ID "$old_frontend_image_id"
    write_shell_kv "$receipt_path" OLD_BACKEND_IMAGE_REF "$old_backend_image_ref"
    write_shell_kv "$receipt_path" OLD_FRONTEND_IMAGE_REF "$old_frontend_image_ref"

    runtime_mutation_started=0
    on_error() {
      local rc="$?"
      trap - ERR
      set +e
      echo "DEPLOY_FAILURE_RC=$rc"
      docker image tag "$old_backend_image_id" "$old_backend_image_ref" >/dev/null 2>&1
      docker image tag "$old_frontend_image_id" "$old_frontend_image_ref" >/dev/null 2>&1
      if [ "$runtime_mutation_started" = "1" ]; then
        if restore_old_images_and_runtime \
          "$project" "$compose_path" "$override_path" \
          "$old_backend_image_id" "$old_backend_image_ref" \
          "$old_frontend_image_id" "$old_frontend_image_ref"; then
          echo "CONTAINER_ROLLBACK=APPLIED"
          write_shell_kv "$receipt_path" DEPLOY_STATUS SAFE_ROLLBACK
          write_shell_kv "$receipt_path" CONTAINER_ROLLBACK APPLIED
        else
          echo "CONTAINER_ROLLBACK=INCOMPLETE"
          write_shell_kv "$receipt_path" DEPLOY_STATUS ROLLBACK_INCOMPLETE
          write_shell_kv "$receipt_path" CONTAINER_ROLLBACK INCOMPLETE
        fi
      else
        echo "CONTAINER_ROLLBACK=NOT_REQUIRED_RUNTIME_UNCHANGED"
        write_shell_kv "$receipt_path" DEPLOY_STATUS BUILD_OR_PREFLIGHT_FAILED_RUNTIME_UNCHANGED
        write_shell_kv "$receipt_path" CONTAINER_ROLLBACK NOT_REQUIRED
      fi
      exit "$rc"
    }
    trap on_error ERR

    cd "$workdir"

    docker compose -p "$project" -f "$compose_path" -f "$override_path" config --quiet
    echo "COMPOSE_OVERRIDE_VALID=YES"

    SIGESC_GIT_SHA="$target_sha" \
      docker compose -p "$project" -f "$compose_path" -f "$override_path" \
      build backend frontend

    built_backend_revision="$(docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$old_backend_image_ref")"
    built_frontend_revision="$(docker image inspect -f '{{ index .Config.Labels "org.opencontainers.image.revision" }}' "$old_frontend_image_ref")"
    [ "$built_backend_revision" = "$target_sha" ] || fail "BUILT_BACKEND_REVISION_MISMATCH"
    [ "$built_frontend_revision" = "$target_sha" ] || fail "BUILT_FRONTEND_REVISION_MISMATCH"
    echo "BUILT_IMAGE_PROVENANCE=PASS"

    runtime_mutation_started=1
    docker compose -p "$project" -f "$compose_path" -f "$override_path" \
      up -d --no-deps --no-build --force-recreate backend
    backend_container="$(wait_service_healthy "$project" backend 300)"

    docker compose -p "$project" -f "$compose_path" -f "$override_path" \
      up -d --no-deps --no-build --force-recreate frontend
    frontend_container="$(wait_service_healthy "$project" frontend 180)"

    mongo_container_after="$(find_service_container "$project" mongo)"
    mongo_container_id_after="$(docker inspect -f '{{.Id}}' "$mongo_container_after")"
    [ "$mongo_container_id_after" = "$mongo_container_id_before" ] \
      || fail "MONGO_CONTAINER_CHANGED"
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$mongo_container_after")" = "healthy" ] \
      || fail "MONGO_NOT_HEALTHY_AFTER_DEPLOY"

    backend_revision="$(image_revision_for_container "$backend_container")"
    frontend_revision="$(image_revision_for_container "$frontend_container")"
    [ "$backend_revision" = "$target_sha" ] || fail "RUNNING_BACKEND_REVISION_MISMATCH"
    [ "$frontend_revision" = "$target_sha" ] || fail "RUNNING_FRONTEND_REVISION_MISMATCH"

    write_shell_kv "$receipt_path" NEW_BACKEND_CONTAINER "$backend_container"
    write_shell_kv "$receipt_path" NEW_FRONTEND_CONTAINER "$frontend_container"
    write_shell_kv "$receipt_path" NEW_BACKEND_IMAGE_ID "$(docker inspect -f '{{.Image}}' "$backend_container")"
    write_shell_kv "$receipt_path" NEW_FRONTEND_IMAGE_ID "$(docker inspect -f '{{.Image}}' "$frontend_container")"
    write_shell_kv "$receipt_path" MONGO_CONTAINER_ID_AFTER "$mongo_container_id_after"
    write_shell_kv "$receipt_path" DEPLOY_STATUS APPLIED_PENDING_PUBLIC_SMOKE

    trap - ERR
    echo "SIGESC_DEPLOY_REMOTE=PASS"
    echo "TARGET_SHA=$target_sha"
    echo "BACKEND_HEALTH=healthy"
    echo "FRONTEND_HEALTH=healthy"
    echo "MONGO_HEALTH=healthy"
    echo "MONGO_CONTAINER_UNCHANGED=YES"
    echo "BACKEND_IMAGE_REVISION=$backend_revision"
    echo "FRONTEND_IMAGE_REVISION=$frontend_revision"
    echo "REMOTE_RECEIPT_PATH=$receipt_path"
    ;;

  finalize)
    [ "$#" -eq 1 ] || fail "FINALIZE_ARGUMENT_COUNT"
    receipt_path="$1"
    [ -f "$receipt_path" ] || fail "RECEIPT_NOT_FOUND"
    case "$receipt_path" in
      /data/coolify/applications/*/.github-deploy/receipts/*.env) ;;
      *) fail "RECEIPT_PATH_INVALID" ;;
    esac
    # shellcheck disable=SC1090
    source "$receipt_path"
    [ "${RECEIPT_SCHEMA:-}" = "SIGESC_GITHUB_ONLY_DEPLOY_V1" ] || fail "RECEIPT_SCHEMA_INVALID"
    [[ "${TARGET_SHA:-}" =~ ^[0-9a-f]{40}$ ]] || fail "FINALIZE_TARGET_SHA_INVALID"

    backend_container="$(wait_service_healthy "$PROJECT" backend 30)" || fail "FINALIZE_BACKEND_NOT_HEALTHY"
    frontend_container="$(wait_service_healthy "$PROJECT" frontend 30)" || fail "FINALIZE_FRONTEND_NOT_HEALTHY"
    mongo_container="$(find_service_container "$PROJECT" mongo)"
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$mongo_container")" = "healthy" ] || fail "FINALIZE_MONGO_NOT_HEALTHY"
    [ "$(docker inspect -f '{{.Id}}' "$mongo_container")" = "$MONGO_CONTAINER_ID_BEFORE" ] || fail "FINALIZE_MONGO_CONTAINER_CHANGED"
    [ "$(image_revision_for_container "$backend_container")" = "$TARGET_SHA" ] || fail "FINALIZE_BACKEND_SHA_MISMATCH"
    [ "$(image_revision_for_container "$frontend_container")" = "$TARGET_SHA" ] || fail "FINALIZE_FRONTEND_SHA_MISMATCH"

    write_shell_kv "$receipt_path" DEPLOY_STATUS APPLIED
    write_shell_kv "$receipt_path" FINAL_RUNTIME_VERIFICATION PASS
    echo "SIGESC_DEPLOY_FINALIZED=APPLIED"
    echo "FINAL_RUNTIME_VERIFICATION=PASS"
    ;;

  rollback)
    [ "$#" -eq 1 ] || fail "ROLLBACK_ARGUMENT_COUNT"
    receipt_path="$1"
    [ -f "$receipt_path" ] || fail "RECEIPT_NOT_FOUND"
    case "$receipt_path" in
      /data/coolify/applications/*/.github-deploy/receipts/*.env) ;;
      *) fail "RECEIPT_PATH_INVALID" ;;
    esac
    # shellcheck disable=SC1090
    source "$receipt_path"

    [ "${RECEIPT_SCHEMA:-}" = "SIGESC_GITHUB_ONLY_DEPLOY_V1" ] || fail "RECEIPT_SCHEMA_INVALID"
    for v in PROJECT COMPOSE_PATH OVERRIDE_PATH OLD_BACKEND_IMAGE_ID OLD_BACKEND_IMAGE_REF OLD_FRONTEND_IMAGE_ID OLD_FRONTEND_IMAGE_REF; do
      [ -n "${!v:-}" ] || fail "ROLLBACK_RECEIPT_FIELD_MISSING_${v}"
    done

    restore_old_images_and_runtime \
      "$PROJECT" "$COMPOSE_PATH" "$OVERRIDE_PATH" \
      "$OLD_BACKEND_IMAGE_ID" "$OLD_BACKEND_IMAGE_REF" \
      "$OLD_FRONTEND_IMAGE_ID" "$OLD_FRONTEND_IMAGE_REF" \
      || fail "ROLLBACK_RUNTIME_RESTORE_FAILED"

    mongo_container="$(find_service_container "$PROJECT" mongo)"
    [ "$(docker inspect -f '{{.Id}}' "$mongo_container")" = "$MONGO_CONTAINER_ID_BEFORE" ] \
      || fail "ROLLBACK_MONGO_CONTAINER_CHANGED"
    [ "$(docker inspect -f '{{.State.Health.Status}}' "$mongo_container")" = "healthy" ] \
      || fail "ROLLBACK_MONGO_NOT_HEALTHY"

    write_shell_kv "$receipt_path" DEPLOY_STATUS SAFE_ROLLBACK
    write_shell_kv "$receipt_path" CONTAINER_ROLLBACK APPLIED
    write_shell_kv "$receipt_path" ROLLBACK_IMAGE_ID_VERIFICATION PASS
    echo "SIGESC_DEPLOY_ROLLBACK=APPLIED"
    echo "ROLLBACK_IMAGE_ID_VERIFICATION=PASS"
    ;;

  *)
    fail "MODE_INVALID"
    ;;
esac
