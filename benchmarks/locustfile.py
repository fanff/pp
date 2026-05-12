import os
import time

from locust import HttpUser, LoadTestShape, between, task


class ThreePhaseShape(LoadTestShape):
    warmup_seconds = int(os.getenv("LOCUST_WARMUP_SECONDS", "120"))
    steady_seconds = int(os.getenv("LOCUST_STEADY_SECONDS", "480"))
    spike_seconds = int(os.getenv("LOCUST_SPIKE_SECONDS", "120"))

    warmup_users = int(os.getenv("LOCUST_WARMUP_USERS", "20"))
    steady_users = int(os.getenv("LOCUST_STEADY_USERS", "80"))
    spike_users = int(os.getenv("LOCUST_SPIKE_USERS", "140"))

    spawn_rate = float(os.getenv("LOCUST_SPAWN_RATE", "10"))

    def tick(self):
        run_time = self.get_run_time()
        warmup_end = self.warmup_seconds
        steady_end = warmup_end + self.steady_seconds
        spike_end = steady_end + self.spike_seconds

        if run_time < warmup_end:
            return self.warmup_users, self.spawn_rate
        if run_time < steady_end:
            return self.steady_users, self.spawn_rate
        if run_time < spike_end:
            return self.spike_users, self.spawn_rate
        return None


class PPApiUser(HttpUser):
    wait_time = between(0.1, 0.5)

    username = os.getenv("PP_BENCH_USERNAME", "admin")
    password = os.getenv("PP_BENCH_PASSWORD", "admin")
    default_conversation_id = int(os.getenv("PP_BENCH_CONVERSATION_ID", "1"))

    def on_start(self):
        self.token = ""
        self.conversation_id = self.default_conversation_id
        self._login()
        self._refresh_conversation_id()

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.token}"}

    def _login(self):
        response = self.client.post(
            "/token",
            data={
                "username": self.username,
                "password": self.password,
                "grant_type": "password",
            },
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            name="POST /token",
        )
        response.raise_for_status()
        self.token = response.json()["access_token"]

    def _refresh_conversation_id(self):
        response = self.client.get("/conv", headers=self._auth_headers(), name="GET /conv")
        if response.status_code != 200:
            return
        body = response.json()
        conversations = body.get("conversations", [])
        if conversations:
            self.conversation_id = conversations[0]["id"]

    @task(35)
    def list_users(self):
        self.client.get("/users", headers=self._auth_headers(), name="GET /users")

    @task(35)
    def list_conversations(self):
        response = self.client.get("/conv", headers=self._auth_headers(), name="GET /conv")
        if response.status_code == 200:
            body = response.json()
            conversations = body.get("conversations", [])
            if conversations:
                self.conversation_id = conversations[0]["id"]

    @task(30)
    def post_message(self):
        payload = {
            "conversation_id": self.conversation_id,
            "content": f"bench-msg-{int(time.time() * 1000)}",
        }
        self.client.post("/usermsg", json=payload, headers=self._auth_headers(), name="POST /usermsg")
