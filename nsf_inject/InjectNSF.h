#ifndef __INJECTNSF_H__
#define __INJECTNSF_H__

#include <vector>
#include <string>
#include <stdint.h>
namespace injectnsf
{
	typedef uint8_t byte;
	using std::vector;
	using std::string;
	bool InjectNSF(const string &fileNname, const string &nsfName, int songNumber);
	vector<byte> ParseNSF(const vector<byte> &nsfData, int &initAddress, int &playAddress);
	vector<byte> InjectNSF(const vector<byte> &inputData, const vector<byte> &nsfData, int songNumber);
}
#endif
