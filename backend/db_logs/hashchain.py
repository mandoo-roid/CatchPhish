{
  "nbformat": 4,
  "nbformat_minor": 0,
  "metadata": {
    "colab": {
      "provenance": [],
      "authorship_tag": "ABX9TyN96riRZ/RlJXLzYpBYn8Fd",
      "include_colab_link": true
    },
    "kernelspec": {
      "name": "python3",
      "display_name": "Python 3"
    },
    "language_info": {
      "name": "python"
    }
  },
  "cells": [
    {
      "cell_type": "markdown",
      "metadata": {
        "id": "view-in-github",
        "colab_type": "text"
      },
      "source": [
        "<a href=\"https://colab.research.google.com/github/seeunppp/CatchPhish/blob/main/hashchain.ipynb\" target=\"_parent\"><img src=\"https://colab.research.google.com/assets/colab-badge.svg\" alt=\"Open In Colab\"/></a>"
      ]
    },
    {
      "cell_type": "code",
      "execution_count": 2,
      "metadata": {
        "colab": {
          "base_uri": "https://localhost:8080/"
        },
        "id": "-iIQiEEDvmoZ",
        "outputId": "2c2433b2-7a48-41c9-f95a-a28d00f2d26f"
      },
      "outputs": [
        {
          "output_type": "stream",
          "name": "stdout",
          "text": [
            "Overwriting hashchain.py\n"
          ]
        }
      ],
      "source": [
        "%%writefile hashchain.py\n",
        "import hashlib, json\n",
        "from datetime import datetime, timezone\n",
        "\n",
        "GENESIS_HASH = \"0\" * 64\n",
        "\n",
        "def canonical(obj):\n",
        "    return json.dumps(obj, sort_keys=True, separators=(\",\", \":\"), ensure_ascii=False)\n",
        "\n",
        "def compute_hash(seq, prev_hash, record, created_at):\n",
        "    body = canonical({\"seq\": seq, \"prev_hash\": prev_hash,\n",
        "                      \"record\": record, \"created_at\": created_at})\n",
        "    return hashlib.sha256(body.encode(\"utf-8\")).hexdigest()\n",
        "\n",
        "def build_entry(prev_entry, record):\n",
        "    seq = 1 if prev_entry is None else prev_entry[\"seq\"] + 1\n",
        "    prev_hash = GENESIS_HASH if prev_entry is None else prev_entry[\"hash\"]\n",
        "    created_at = datetime.now(timezone.utc).isoformat()\n",
        "    return {\"seq\": seq, \"prev_hash\": prev_hash, \"record\": record,\n",
        "            \"created_at\": created_at,\n",
        "            \"hash\": compute_hash(seq, prev_hash, record, created_at)}\n",
        "\n",
        "def verify_chain(entries):\n",
        "    prev_hash = GENESIS_HASH\n",
        "    for i, e in enumerate(entries, start=1):\n",
        "        if e[\"seq\"] != i:\n",
        "            return {\"ok\": False, \"broken_seq\": i, \"reason\": \"순번이 끊김 (기록 삭제·삽입 의심)\"}\n",
        "        if e[\"prev_hash\"] != prev_hash:\n",
        "            return {\"ok\": False, \"broken_seq\": i, \"reason\": \"앞 기록의 지문이 안 맞음\"}\n",
        "        if compute_hash(e[\"seq\"], e[\"prev_hash\"], e[\"record\"], e[\"created_at\"]) != e[\"hash\"]:\n",
        "            return {\"ok\": False, \"broken_seq\": i, \"reason\": \"기록 내용이 바뀜 (변조)\"}\n",
        "        prev_hash = e[\"hash\"]\n",
        "    return {\"ok\": True, \"count\": len(entries)}"
      ]
    },
    {
      "cell_type": "code",
      "source": [
        "import copy\n",
        "from hashchain import build_entry, verify_chain\n",
        "\n",
        "chain, prev = [], None\n",
        "for i in range(1, 4):\n",
        "    record = {\"anon_id\": \"U7F3A\", \"job\": \"hr\", \"scenario_id\": f\"S0{i}\",\n",
        "              \"choice\": \"click\", \"is_correct\": False,\n",
        "              \"analysis\": {\"type\": \"url\", \"score\": 60}}\n",
        "    prev = build_entry(prev, record)\n",
        "    chain.append(prev)\n",
        "\n",
        "print(\"1) 정상:\", verify_chain(chain))\n",
        "t = copy.deepcopy(chain); t[1][\"record\"][\"is_correct\"] = True\n",
        "print(\"2) 2번 기록 수정:\", verify_chain(t))\n",
        "t = copy.deepcopy(chain); del t[1]\n",
        "print(\"3) 2번 기록 삭제:\", verify_chain(t))"
      ],
      "metadata": {
        "colab": {
          "base_uri": "https://localhost:8080/"
        },
        "id": "UyTy6GGYwXvR",
        "outputId": "ccf92991-1a09-4890-8225-6b7f6679aa54"
      },
      "execution_count": 3,
      "outputs": [
        {
          "output_type": "stream",
          "name": "stdout",
          "text": [
            "1) 정상: {'ok': True, 'count': 3}\n",
            "2) 2번 기록 수정: {'ok': False, 'broken_seq': 2, 'reason': '기록 내용이 바뀜 (변조)'}\n",
            "3) 2번 기록 삭제: {'ok': False, 'broken_seq': 2, 'reason': '순번이 끊김 (기록 삭제·삽입 의심)'}\n"
          ]
        }
      ]
    }
  ]
}
