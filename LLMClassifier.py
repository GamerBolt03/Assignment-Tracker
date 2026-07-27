import os
import threading


class LLMClassifier:
    MODELS = {
        "distilbert": {
            "name": "typeform/distilbert-base-uncased-mnli",
            "size": "260MB",
            "type": "zero-shot"
        },
        "gemma-2b": {
            "name": "google/gemma-2b-it",
            "size": "3.1GB",
            "type": "text-gen"
        }
    }

    def __init__(self):
        self._classifier = None
        self._current_model = None
        self._ready = False
        self._error = None

    def is_ready(self):
        return self._ready

    def get_current_model(self):
        return self._current_model

    def _setup_ssl(self):
        os.environ['HF_HUB_DISABLE_SSL_VERIFY'] = '1'
        os.environ['CURL_CA_BUNDLE'] = ''
        os.environ['REQUESTS_CA_BUNDLE'] = ''

        import requests
        requests.packages.urllib3.disable_warnings()

        from huggingface_hub import configure_http_backend
        def backend():
            s = requests.Session()
            s.verify = False
            return s
        configure_http_backend(backend)

    @staticmethod
    def get_hf_cache_dir():
        default = os.path.expanduser("~/.cache/huggingface/hub")
        return os.environ.get("HUGGINGFACE_HUB_CACHE") or os.environ.get("HF_HOME") or default

    @staticmethod
    def check_cached(model_key):
        from huggingface_hub import HfApi
        model_info = LLMClassifier.MODELS.get(model_key)
        if not model_info:
            return False
        model_name = model_info["name"]
        cache_dir = LLMClassifier.get_hf_cache_dir()
        cache_subdir = "models--" + model_name.replace("/", "--")
        subdir = os.path.join(cache_dir, cache_subdir, "snapshots")
        return os.path.isdir(subdir) and len(os.listdir(subdir)) > 0

    @staticmethod
    def check_all_cached():
        return {k: LLMClassifier.check_cached(k) for k in LLMClassifier.MODELS}

    def load(self, model_key="distilbert"):
        self._setup_ssl()

        model_info = self.MODELS.get(model_key)
        if not model_info:
            self._ready = False
            self._error = f"Unknown model: {model_key}"
            return

        model_name = model_info["name"]
        model_type = model_info["type"]
        self._current_model = model_key

        try:
            from transformers import pipeline

            if model_type == "zero-shot":
                self._classifier = pipeline(
                    "zero-shot-classification",
                    model=model_name
                )
            elif model_type == "text-gen":
                from transformers import AutoModelForCausalLM, AutoTokenizer
                tokenizer = AutoTokenizer.from_pretrained(model_name)
                model = AutoModelForCausalLM.from_pretrained(
                    model_name, device_map="auto"
                )
                self._classifier = {"model": model, "tokenizer": tokenizer}
            else:
                self._classifier = pipeline(
                    "zero-shot-classification",
                    model=model_name
                )

            self._ready = True
            self._error = None
        except Exception as e:
            self._ready = False
            self._error = str(e)

    def unload(self):
        self._classifier = None
        self._current_model = None
        self._ready = False
        self._error = None

    def is_assignment(self, subject, body):
        if not self._ready or not self._classifier:
            return False

        model_info = self.MODELS.get(self._current_model, {})
        model_type = model_info.get("type", "zero-shot")

        try:
            if model_type == "zero-shot":
                text = f"{subject} {body}"[:512]
                result = self._classifier(
                    text,
                    candidate_labels=[
                        "school assignment", "homework task", "academic project",
                        "course work", "class exercise", "lab report",
                        "personal email", "notification", "promotional email",
                        "social media", "security alert", "receipt",
                        "invitation", "newsletter", "meeting reminder"
                    ],
                )
                assign_labels = {
                    "school assignment", "homework task", "academic project",
                    "course work", "class exercise", "lab report"
                }
                return result['labels'][0] in assign_labels and result['scores'][0] > 0.35

            elif model_type == "text-gen":
                prompt = f"""[INST] You are classifying emails as either assignment-related or not.
An assignment email is about homework, projects, exams, coursework, lab reports, or other academic tasks.

Classify this email:
Subject: {subject}
Body: {body[:500]}

Reply with exactly one word: ASSIGNMENT or NOT_ASSIGNMENT [/INST]"""
                inputs = self._classifier["tokenizer"](prompt, return_tensors="pt", truncation=True)
                outputs = self._classifier["model"].generate(
                    **inputs, max_new_tokens=10, do_sample=False
                )
                result = self._classifier["tokenizer"].decode(
                    outputs[0], skip_special_tokens=True
                )
                return "ASSIGNMENT" in result.split("[/INST]")[-1].strip().upper()

            return False
        except Exception:
            return False
