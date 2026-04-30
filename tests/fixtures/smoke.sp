fn add(a: I32, b: I32) -> I32
spec {
    example "basic": add(20, 22) == 42
}
{ a + b }
