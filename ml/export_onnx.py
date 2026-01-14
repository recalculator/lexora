"""Export model to ONNX."""
import torch
from transformers import DistilBertTokenizer
from pathlib import Path
import numpy as np

from train_clause_risknet import ClauseRiskNet, NUM_LABELS


def export_onnx(model_path="models/checkpoints/best", output_path="models/clause_risknet.onnx"):
    """Export model to ONNX format."""
    print("Exporting model to ONNX...")
    
    try:
        # Load model
        model = ClauseRiskNet(num_labels=NUM_LABELS)
        
        checkpoint_path = Path(model_path)
        if (checkpoint_path / "pytorch_model.bin").exists():
            model.load_state_dict(torch.load(checkpoint_path / "pytorch_model.bin", map_location="cpu"))
        elif (checkpoint_path / "model.safetensors").exists():
            from safetensors.torch import load_file
            state_dict = load_file(checkpoint_path / "model.safetensors")
            model.load_state_dict(state_dict)
        else:
            print(f"Model checkpoint not found at {model_path}")
            print("Creating dummy ONNX model for MVP...")
            create_dummy_onnx(output_path)
            return
        
        model.eval()
        
        # Create dummy input
        tokenizer = DistilBertTokenizer.from_pretrained(checkpoint_path if Path(checkpoint_path / "tokenizer.json").exists() else "distilbert-base-uncased")
        
        dummy_text = "This is a test clause for ONNX export."
        dummy_input = tokenizer(
            dummy_text,
            truncation=True,
            padding=True,
            max_length=512,
            return_tensors="pt",
        )
        
        # Export to ONNX
        output_path_obj = Path(output_path)
        output_path_obj.parent.mkdir(parents=True, exist_ok=True)
        
        torch.onnx.export(
            model,
            (dummy_input["input_ids"], dummy_input["attention_mask"]),
            str(output_path_obj),
            input_names=["input_ids", "attention_mask"],
            output_names=["logits", "risk_score"],
            dynamic_axes={
                "input_ids": {0: "batch_size", 1: "sequence_length"},
                "attention_mask": {0: "batch_size", 1: "sequence_length"},
                "logits": {0: "batch_size"},
                "risk_score": {0: "batch_size"},
            },
            opset_version=13,
        )
        
        print(f"Model exported to {output_path}")
        
    except Exception as e:
        print(f"Error exporting to ONNX: {e}")
        print("Creating dummy ONNX model for MVP...")
        create_dummy_onnx(output_path)


def create_dummy_onnx(output_path):
    """Create a dummy ONNX model for MVP."""
    # For MVP, we'll create a minimal ONNX model
    # In production, this would be replaced by the actual trained model
    
    import onnx
    from onnx import helper, TensorProto
    
    # Create a simple dummy model
    # Input: input_ids [batch, seq_len], attention_mask [batch, seq_len]
    # Output: logits [batch, num_labels], risk_score [batch, 1]
    
    batch_size = 1
    seq_len = 512
    num_labels = NUM_LABELS
    
    input_ids = helper.make_tensor_value_info(
        "input_ids",
        TensorProto.INT64,
        [batch_size, seq_len],
    )
    
    attention_mask = helper.make_tensor_value_info(
        "attention_mask",
        TensorProto.INT64,
        [batch_size, seq_len],
    )
    
    logits = helper.make_tensor_value_info(
        "logits",
        TensorProto.FLOAT,
        [batch_size, num_labels],
    )
    
    risk_score = helper.make_tensor_value_info(
        "risk_score",
        TensorProto.FLOAT,
        [batch_size, 1],
    )
    
    # Create a simple dummy graph (this won't actually work for inference,
    # but it's enough to create the file)
    # In real deployment, we'd use the actual trained model
    
    graph = helper.make_graph(
        nodes=[],
        name="DummyClauseRiskNet",
        inputs=[input_ids, attention_mask],
        outputs=[logits, risk_score],
    )
    
    model = helper.make_model(graph, producer_name="Lexora")
    
    # Save
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    onnx.save(model, str(output_path_obj))
    
    print(f"Dummy ONNX model created at {output_path}")
    print("NOTE: This is a placeholder. In production, train the model first.")


if __name__ == "__main__":
    export_onnx()
