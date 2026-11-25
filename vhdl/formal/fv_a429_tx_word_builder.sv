// Formal doğrulama: a429_tx_word_builder (tüm 2^32 giriş kombinasyonu için tam ispat)
`default_nettype none
module fv_a429_tx_word_builder (
    input  wire [7:0]  label_val,
    input  wire [1:0]  sdi,
    input  wire [18:0] data,
    input  wire [1:0]  ssm,
    input  wire        parity_type
);
    wire [31:0] word_out;

    a429_tx_word_builder dut (
        .label_val   (label_val),
        .sdi         (sdi),
        .data        (data),
        .ssm         (ssm),
        .parity_type (parity_type),
        .word_out    (word_out)
    );

    always @(*) begin
        // P1: Alan yerleşimi birebir doğru
        assert(word_out[7:0]   == label_val);
        assert(word_out[9:8]   == sdi);
        assert(word_out[28:10] == data);
        assert(word_out[30:29] == ssm);
        // P2 & P3: Odd (1) ve Even (0) parity tüm 2^32 kombinasyonda eksiksiz sağlanır
        if (parity_type)
            assert(^word_out == 1'b1);
        else
            assert(^word_out == 1'b0);
    end
endmodule
