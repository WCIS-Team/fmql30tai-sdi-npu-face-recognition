#pragma once
#include <cstdint>
#include <stdexcept>
#include <vector>

// Same FP32 NHWC values as the existing NumPy contract. Input is FAC1's
// validated little-endian BGRX output; the NPU graph/weights do not change.
inline std::vector<float> wcis_prepare_input(const std::vector<char>& pixels,bool recognizer){
 if(pixels.empty()||pixels.size()%4)throw std::runtime_error("Invalid BGRX tensor preparation length");
 std::vector<float> values(pixels.size()/4*3);
 for(size_t i=0;i<pixels.size()/4;++i)for(unsigned channel=0;channel<3;++channel){
  const auto value=static_cast<unsigned char>(pixels[i*4+(recognizer?2-channel:channel)]);
  const float number=static_cast<float>(value);
  values[i*3+channel]=recognizer?(number-127.5f)/127.5f:number;
 }
 return values;
}
