import opengradient as og

client = og.Client(
    private_key="0xafdf410b420960cd54092f8c18f0d8b31ba701c9d030531d7a3e37ce904661e8"
)

client.llm.ensure_opg_approval(opg_amount=5.0)

result = client.llm.chat(
    model=og.TEE_LLM.GEMINI_2_5_FLASH,
    messages=[
        {"role": "user", "content": "What is Ethereum in one sentence?"}
    ],
    max_tokens=100
)

print(f"Response: {result.chat_output['content']}")
print(f"Payment hash: {result.payment_hash}")